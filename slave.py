import serial
import logging
import csv
import cStringIO
import reedsolo
import time
import os
import math
import random

################ SETUP

# Logging init
logging.basicConfig(
    filename='slave.log',
    format='%(asctime)s %(message)s',
    datefmt='%m/%d/%Y %I:%M:%S %p',
    level=logging.DEBUG
    )

# Set up serial port
ser = serial.Serial(
    port='/dev/ttyAMA0',
    baudrate=921600,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    #inter_byte_timeout=0.1,
    timeout=0
)

# Init precomputed tables for Reed Solomon
reedsolo.init_tables(0x11d)

# Pre-generation of polynomials for faster encoding
gen=reedsolo.rs_generator_poly_all(19)

################ DEFINES

# Protocol bytes
ACK = b'\x07'
NAK = b'\x08'
ack_pack = reedsolo.rs_encode_msg(ACK, 2, 0, 2, gen[2])
nak_pack = reedsolo.rs_encode_msg(NAK, 2, 0, 2, gen[2])
#For send mode a cancel with packet length must be issued to be recognized by the receiver

# Relative location of the AUV.
# For simulation purposes, randomize the location
loc=[random.randint(10,179), random.randint(0,30)]

# Error map file (CSV)
mapFile='error_map_slave'

# Timout management
TOUT_recv=0.7 # Timeout seconds for ARQ system
TOUT_send=0.5 # Timeout seconds for send function

# Limits of the packets (SER)
lim236 = 0.0179
lim64 = 0.0596

# Updater vars
updater_n = 200
updater_tol = 6
# Init circular buffer
updater_buf = [-1 for init1 in range(updater_n)]
updater_prob = 0
updater_count = 0
updater_key = 1
updater_lastloc = loc

############################################

# Shutdown properly
def shutdown():
    logging.debug('Shutdown request')
    logging.shutdown()
    ser.flushOutput()
    ser.flushInput()
    ser.close()
    exit()

# Init function
def init():
    # Serial port initialization
    if ser.isOpen():
        try:
            ser.flushInput() #flush input buffer
            ser.flushOutput()#flush output buffer
        except Exception, ef:
            print ("Error flushing buffers")
            logging.error("Error flushing buffers")
            return 0
    else:
        print ("Error opening serial port")
        logging.error("Error opening serial port")
        return 0
        
    return 1

# Factorial of a number
def factorial(n):return reduce(lambda x,y:x*y,[1]+range(1,n+1))

# Calculation of packet decoding error probability (binomial form)
def PDEP(p, N, nk):
    min = (nk/2)+1
    pdep=0
    for k in range(min, N+1):
        # Calculate PDP with the formula from literature
        pdep += (float(factorial(N))/(factorial(k)*factorial(N-k)))*(p**k)*((1-p)**(N-k))
    
    return pdep

# Cumulative distribution function
def CDF(x):
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

# Approximation of binomial cdf with continuity correction
def NPDEP(p, N, nk):
    min = (nk/2)+1 
    return 1-CDF((min-0.5-(N*p))/math.sqrt(N*p*(1-p)))

# Iteration of the best N-K values
def NK(p, K):
    nkarr= [0] * 9
    for i in range(9):
        nk = (i+1)*2
        if K >= 100:
            nkarr[i] += (float(K)/(nk+K)) * (1-NPDEP(p, (K+nk), nk))
        else:
            nkarr[i] += (float(K)/(nk+K)) * (1-PDEP(p, (K+nk), nk))
    
    nk = (nkarr.index(max(nkarr))+1)*2
    
    # Limit packets of 237 to 4 bytes to avoid singleton bound errors
    return nk+2 if nk<=2 and K>=100 else nk

# Interpolate the locations given by the AUV so that it's possible to group the ByER (byte error rate)
# for the angle, it's divided in two parts: from 0~20 and >20
# for the height, it is grouped in steps of 10cm.
# all of the values on the error map might be changed with ease in the future.
def interpolate():
    if loc == [None, None]:
        return [None, None]
    else:
        grouph = int(math.floor(float(loc[0])/10)*10)
        groupa = 0 if loc[1]<20 else 20
        return [grouph, groupa]

# Search inside the csv file for the location
# Error map file structure:
# [Height group], [Angle group], [Initial error rate]
def get_fec():
    l = interpolate()
    if l == [None, None]:
        return 0
    
    reader = csv.reader(open(mapFile+'.csv', 'rb'), delimiter=',')
    for row in reader:
        if l[0]==int(row[0]) and l[1]==int(row[1]): #col 1 and 2
            return float(row[2])
        
    return 0

# Updater ( Error-correction control )
# Checks last updater_n bytes to see if there is a discrepancy between the amount of NAKs and ACKs, based on the probability of packet error
# type: 0 if NAK, 1 if ACK
def updater(type, p=0):
    global updater_buf
    global updater_count
    global updater_key
    global updater_prob
    global updater_lastloc
    
    # Check if location changed first and reset if it has
    if loc != updater_lastloc:
        updater_key = 1
        updater_count = 0
        updater_buf = [-1 for new in range(updater_n)]
        updater_lastloc = loc
        
    if updater_key and p>0:
        if p < lim236:
            nk = NK(p, 237)
            updater_prob = NPDEP(p, 237+nk, nk)
        elif p < lim64:
            nk = NK(p, 65)
            updater_prob = PDEP(p, 65+nk, nk)
        else:
            nk = NK(p, 9)
            updater_prob = PDEP(p, 9+nk, nk)
        updater_key = 0
            
    # Update buffer
    if updater_count == 0:
        updater_buf[updater_buf.index(-1)] = type
        
        # Check if buffer full
        if -1 not in updater_buf:
            cnt = updater_buf.count(0)
            if cnt > updater_prob * updater_n + round(updater_tol/2.0):
                updater_count += 2
            elif cnt < updater_prob * updater_n - round(updater_tol/2.0) :
                updater_count -= 2

# Non-blocking header read with variable timeouts.
# tout: timeout value
# returns: header decoded, error, or None
def hread(tout):
    start = time.time()
    while tout<=0 or (time.time() - start) < tout:
        if ser.inWaiting() >= 3:
            try:
                header = reedsolo.rs_correct_msg(ser.read(3), 2)[0]
                
                return ord(header)
            except reedsolo.ReedSolomonError as e:
                return 'Error'
            
    ser.flushInput
    return None

# Non-blocking header read with variable timeouts.
# val: amount of bytes to read
# returns: packet read, error or None
def pread(val):
    # If it's a retransmission, pass the value to 2
    if val == 3:
        val = 2
    start = time.time()
    while time.time() - start < TOUT_recv:
        if ser.inWaiting() >= val:
            return ser.read(val)
            
    ser.flushInput
    return None

# Terminator of a communication exchange
# Reads until timeout and if something is read then send a response accordingly
# mode: 1- ACK, 0 - NAK
def terminator(mode):
    while True:
        r = hread(TOUT_recv)
        if r!=0 and r!=None:
            if mode==1: #ACK
                ser.write(ack_pack)
            else:
                ser.write(nak_pack)
        else:
            return

# Get data when a request is sent
def get_data(header):
    seq_last=int(100) # Random number different from 1
    buffer=[]
    retr_seq = 0 # Retransmission sequence
    
    while True:
        if header=='Error':
            ser.flushInput()
            ser.write(nak_pack)
            header=hread(TOUT_recv)
            continue
        elif 6 < header < 9:
            # It is an ACK or a NAK
            print("In function get_data: Expected data, ARQ response found")
            logging.critical("In function get_data: Expected data, ARQ response found")
            return None
        else:
            break
    
    while True:
        temp = pread(header)
        if temp==None:
            print("In function get_data: Expected packet")
            logging.critical("In function get_data: Expected packet")
            return None
        
        # Check if it's a retransmission
        if 2 <= header <= 3:
            # It's a retransmission
            if retr_seq != header: # Append the FEC symbols only if the sequence is different from the last one
                packet += temp
                header = len(packet)
        else:
            packet = temp
        
        # Calculate N-K based on packet length
        if header >= 237: # 236+1 packet
            dlength = 237
        elif 65 <= header < 237: # 64+1 packet
            dlength = 65
        else: # 8+1 packet
            dlength = 9
            
        nk = header-dlength
        
        # header = data + current FEC
        # dlength = data
        # nk = FEC
        # dlength + 18 = max packet
        try:
            # Parse sequence number and data
            if nk>0:
                rs_packet=packet + ''.join('0' for x in range(18-nk))
                p = reedsolo.rs_correct_msg(rs_packet, 18, 0, 2, [i for i in range(header,(dlength+18))])[0]
                seq = p[0]
                data = p[1:]
            else:
                seq = ord(packet[0])
                data= packet[1:]
            
            if seq!=seq_last:
                # Remove zeros padded for last packet
                if 0 < seq <= 7:
                    data=data[:-seq]
                    
                buffer.append(data.decode('utf-8'))
                seq_last=seq
                
            if seq <= 7:
                return b"".join(buffer)
            
            # Reset retransmission sequence
            retr_seq = 0
            # Send ACK
            ser.write(ack_pack)
            
        except (reedsolo.ReedSolomonError, ZeroDivisionError):
            # Send NAK
            ser.write(nak_pack)
            
            if nk==18: # Maximum FEC bytes reached
                print("In function get_data: Maximum NAK reached")
                logging.critical("In function get_data: Maximum NAK reached")
                terminator(0) # Respond to communication attempts by sending out a NAK
                return None
        
        # Read header
        while True:
            header = hread(TOUT_recv)
            
            if header==None:
                print("In function get_data: Connection timed out")
                logging.critical("In function get_data: Connection timed out")
                return None
            elif header=='Error':
                ser.flushInput()
                ser.write(nak_pack)
                continue
            elif 6 < header < 9:
                # It is an ACK or a NAK
                print("In function get_data: Expected data, ARQ response found")
                logging.critical("In function get_data: Expected data, ARQ response found")
                return None
            else:
                break

# Loop to test the timeout on the send function
def send_loop_tout(packet):
    tout_count=0
    while True:
        # Send packet
        ser.write(packet)
        
        # Get the answer from the AUV
        while True:
            answer = hread(TOUT_send)
            if answer==None:
                tout_count+=1
                if tout_count > 1:
                    updater(0)
                
                # Test for timeout count
                if tout_count>=2:
                    return None
                else:
                    break
            else:
                return answer

# Send function:
# stream: data stream to send
# length: length of the object
# type: 0- string, 1- file stream
def send(stream, length, type=0):
    # Initializing the stream
    if not type:
        stream=cStringIO.StringIO(stream)
    
    # Sequence init
    seq = 20
    
    # FEC rate calculation and packet distribution from error map
    fec_rate=get_fec()
    updater(-1, fec_rate)
    
    # Divide the data into packets.
    # As the maximum FEC bytes allowed in a packet is 18, the maximum fec bytes to add to a 8+1
    # message is 18 (corrects 9 errors, fec rate becomes 1).
    # With the same reasoning, on a 64+1 packet, the maximum code rate is 0.13, and for
    # a 236+1 packet it becomes 0.03. However, limitations should be done in order to prevent
    # errors with the ARQ system, so the code rate should be lower than the actual maximum to allow
    # NAKs to be used.
    data236 = 0.0
    data64 = 0.0
    data8 = 0.0
    if fec_rate < lim236:
        data236 = math.floor(length/236)
        data64 = math.floor((length%236)/64.0)
        data8 = math.ceil(((length%236)%64)/8.0)
    elif fec_rate < lim64:
        data64 = math.floor(length/64.0)
        data8 = math.ceil((length%64)/8.0)
    else:
        data8 = math.ceil(length/8.0)
    
    # Send packets loop
    while True:
        # Declare data packet sizes
        if data236 > 0:
            data = stream.read(236)
            data236 -= 1
        elif data64 > 0:
            data = stream.read(64)
            data64 -= 1
        elif data8 > 0:
            data = stream.read(8)
            data8 -= 1
            
            # Last 8 bytes
            if (data236+data64+data8) == 0:
                # For last packet, sequence number = 8 - len(data)
                seq = 8 - len(data)
                data = data + ((8 - len(data))*'\x00')
        else:
            return 1
        # From this block get: data / len(data)
        
        # Alternate sequence number if not last packet
        if seq >= 9:
            seq=8
        elif seq == 8:
            seq=9
        # From this block get: seq (1 byte)
        
        # How many FEC bytes to add to the packet? FEC must be multiples of 2 for error correction
        fec_bytes = NK(fec_rate, (len(data)+1)) + updater_count
        
        if fec_bytes > 18:
            fec_bytes = 18
        elif fec_bytes < 2:
            fec_bytes = 2
        
        #Init vars
        nak_count = 0
        first_packet = []
        
        #NAK loop
        while True:
            # Send two bytes of FEC for every count of NAK
            if nak_count > 0:
                fec_bytes+=2
            
            # Detect maximum and minimum of fec bytes
            if fec_bytes == 0:
                fec_bytes = 2
            elif fec_bytes > 18:
                logging.critical('In function send(): FEC bytes reached maximum')
                print ("In function send(): FEC bytes already maximum")
                return None
            # From this block get: fec_bytes (number of fec_bytes to add)
            
            # Encode packet with fec_bytes bytes
            # Pre-process Reed-Solomon packet with full 18 bytes
            if nak_count > 0:
                # Send only the two bytes needed (Hybrid ARQ IR)
                fec_packet = first_packet[-(18-fec_bytes+2):-(18-fec_bytes)] if fec_bytes < 18 else first_packet[-2:]
            else:
                first_packet = reedsolo.rs_encode_msg(chr(seq)+data, 18, 0, 2, gen[18])
                if fec_bytes == 18:
                    fec_packet = first_packet
                else:
                    fec_packet = first_packet[0:-(18-fec_bytes)]
            # From this block get: packet (final packet containing seq + msg + cobs + fec
            
            # Add header according to packet (alternate as the seq number for retransmissions)
            packet=reedsolo.rs_encode_msg(chr(len(fec_packet)+(nak_count%2)), 2, 0, 2, gen[2])
            packet.extend(fec_packet)
            # Sending of packet and timeout checking
            answer = send_loop_tout(packet)
            if answer == None:
                # Header returned None
                logging.critical("In function send(): Max timeouts while getting response.")
                print("Timeout while sending data")
                return None
            elif answer == 'Error':
                # Header undecodable
                nak_count+=1
                if nak_count > 1:
                    updater(0)
                continue
            
            # Parse and decode answer - if undecodable resend packet
            if answer == ord(ACK):
                if nak_count == 0:
                    # Update only if it's within the various packets' range
                    if (fec_rate < lim236 and data236 > 0) or (lim236 <= fec_rate < lim64 and data64 > 0) or (fec_rate >= lim64):
                        updater(1)
                break
            elif answer == ord(NAK):
                nak_count+=1
                if nak_count == 1:
                    # Update only if it's within the various packets' range
                    if (fec_rate < lim236 and data236 > 0) or (lim236 <= fec_rate < lim64 and data64 > 0) or (fec_rate >= lim64):
                        updater(0)

def main():
    if init()==0:
        shutdown()
    
    while True:
        # Read indefinitely
        reader= hread(0)
        if reader==0:
            ser.flushInput()
            continue
        
        # Read data
        data=get_data(reader)
        
        if data==None:
            continue
        else:
            data=data.split() # Get command
            
        # Parse data
        if data[0]=='gl':
            tosend=str(loc[0]) + " " + str(loc[1])
            send(tosend, len(tosend))
        elif data[0]=='fg':
            if data[1]!=None and os.path.isfile(data[1]):
                send(open(data[1], 'rb'), os.stat(data[1]).st_size, type=1)
            else:
                continue
        elif data[0]=='sm':
            # ACK needs to be sent, as there is no DATA to send
            ser.write(ack_pack)
            terminator(1)
            print('Message sent from master: %s' % ' '.join(data[1:]))
            logging.debug('Message sent from master: %s' % ' '.join(data[1:]))
        else:
            terminator(1) # Send ACK

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        shutdown()