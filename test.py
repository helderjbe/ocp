import reedsolo
import random

# Factorial of a number
def factorial(n):return reduce(lambda x,y:x*y,[1]+range(1,n+1))

# Calculation of packet decoding error probability
def PDEP(p, N, nk):
    min = (nk/2)+1
    pdep=0
    for k in range(min, N+1):
        pdep += (float(factorial(N))/(factorial(k)*factorial(N-k)))*(p**k)*((1-p)**(N-k))
    
    return pdep

# Init reedsolomon tables
reedsolo.init_tables(0x11d)

# Probability of error
pe = 0.08

# Number of trials
n= 100

# Number of packets to test
narr= 1

# Packet to be tested
nk = 2
packet=reedsolo.rs_encode_msg('123456789', nk)
l=len(packet)

# Decoding number array
dec=[0] * n

# Get theoretical values
# Probabilities of decoding
pt = 1-PDEP(pe, l, nk)
# Multiply by packets
dect= pt*narr

for num in range(n):    
    # Simulation loop
    for i in range(narr):
        en = packet[:]
        # Channel simulation
        for x,y in enumerate(en):
            # Add errors based on probability to be tested
            if random.random() < pe:
                # Avoid writing a symbol that is the same as the original
                if en[x]!=1:
                    en[x]=1
                else:
                    en[x]=0
            
        # Test if decodable
        try:
            de = reedsolo.rs_correct_msg(en, nk)[0]
            # Correct decoding?
            if de == packet[:-nk]:
                dec[num]+=1
        except reedsolo.ReedSolomonError:
            continue
    
# dec - Decoded number
# dect - Theoretical value
print max(dec)-dect
print min(dec)-dect