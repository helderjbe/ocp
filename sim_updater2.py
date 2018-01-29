import reedsolo
import random
import matplotlib
matplotlib.use("Pdf")
import matplotlib.pyplot as plt
import math

# Probability of errors
notpe = 0.08
pe = 0.1

# Updater vars
updater_n = 1000
updater_tol = 33
# Init circular buffer
updater_buf = [-1 for init1 in range(updater_n)]
updater_prob = 0
updater_count = 0
updater_key = 1

def updater(type):
    global updater_buf
    global updater_count
    global updater_key
    global updater_prob
    
    # Check if location changed first
    if updater_key:
        if notpe < 0.0179:
            nk = NK(notpe, 237)
            updater_prob = NPDEP(notpe, 237+nk, nk)
        elif notpe < 0.0596:
            nk = NK(notpe, 65)
            updater_prob = PDEP(notpe, 65+nk, nk)
        else:
            nk = NK(notpe, 9)
            updater_prob = PDEP(notpe, 9+nk, nk)
        updater_key = 0
            
    # Update buffer
    if updater_count == 0:
        updater_buf[updater_buf.index(-1)] = type
    
    if -1 not in updater_buf:
        cnt = updater_buf.count(0)
        print cnt
        print updater_prob * updater_n
        if cnt > updater_prob * updater_n + updater_tol:
            updater_count += 2
        elif cnt < updater_prob * updater_n - updater_tol :
            updater_count -= 2
        updater_buf = [-1 for new in range(updater_n)]

# Factorial of a number
def factorial(n):return reduce(lambda x,y:x*y,[1]+range(1,n+1))

# Calculation of packet decoding error probability
def PDEP(p, N, nk):
    min = (nk/2)+1
    pdep=0
    for k in range(min, N+1):
        # Calculate PDP with the formula from literature
        pdep += (float(factorial(N))/(factorial(k)*factorial(N-k)))*(p**k)*((1-p)**(N-k))
    
    return pdep

# Cumulative distribution function
def CDF(x):
    return (1.0 + math.erf(x/math.sqrt(2.0)))/ 2.0

def NPDEP(p, N, nk):
    min = (nk/2)+1 
    # Approximation of binomial cdf with continuity correction
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

# Init
reedsolo.init_tables(0x11d)

# Number of packets to test
n= 2000

p=reedsolo.rs_encode_msg('1234'*2+'1', 18)

# Simulation loop
dectry=[0] * n
idec=[0] * n
naks=[0] * (n/10)
nsym=[0] * n
terr=[0] * n
nfec=[0] * n

for j in range(n):
    nki = NK(notpe, 9) + updater_count

    nak_count=0
    nfec[j]=nki
    en=[]
    nk=0
    while True:
            nk=nki + nak_count*2
            
            if nak_count > 0:
                # Send only the two bytes needed (Hybrid ARQ IR)
                en = p[-(18-nk+2):-(18-nk)] if nk < 18 else p[-2:]
            else:
                if nk == 18:
                    en = p[:]
                else:
                    en = p[0:-(18-nk)]
                
            for x,y in enumerate(en):
                # Add errors
                if random.random() < pe:
                    if en[x]!=1:
                        en[x]=1
                    else:
                        en[x]=0
                
            if len(en) > 2:
                todec = en[:]
            else:
                todec += en[:]
                
            # Decode    
            try:
                #FEC
                
                rs_packet=todec[:] + ''.join('0' for x in range(18-nk))
                de = reedsolo.rs_correct_msg(rs_packet, 18, 0, 2, [rs for rs in range(len(todec),(len(todec)+(18-nk)))])[0]
                # Correct decoding?
                if de == p[:-18]:
                    dectry[j]+=1
                    if nak_count <= 0:
                        updater(1)
                else:
                    idec[j]+=1
    
                break
            except (reedsolo.ReedSolomonError, ZeroDivisionError):
                nak_count+=1
                if nak_count == 1:
                    updater(0)
                if (nki + nak_count*2) > 18:
                    break
                
                naks[int(math.floor(float(j)/(n/10)))]+=1
            
# Plotting decoded packets
print ('Plotting...')
fig, ax = plt.subplots()
#ax.plot(pe, [(ndec[plt1]/float(n))*100 for plt1 in range(len(pe))], 'k--', label="Uncoded")
#ax.plot([np1+1 for np1 in range(n)], dectry, 'k-', label="Proposed")
#count the numbers in list
count = []
#ax.bar([np8+1 for np8 in range(n)], [100*float(naks[int(math.ceil(float(np10)/n))])/max(naks) for np10 in range(n)], width=0.97, align='edge', color='black')
ax.plot([np8+1 for np8 in range(n)], [100*float(naks[int(math.floor(float(np10)/(n/10)))])/max(naks) for np10 in range(n)], 'k-')
ax.plot([np2+1 for np2 in range(n)], [50 for asd in range(n)], 'k--', label="Intended")
ax.legend(loc=0)
plt.axis([0, n, 0, 100])
plt.xscale('linear')
plt.yscale('linear')
plt.xlabel('Packet number')
plt.ylabel('2nd retransmissions (%)')
plt.grid(True)
print ('Saving...')
plt.savefig('sim-updater-naks.jpg', bbox_inches='tight')

# Plotting decoded packets
print ('Plotting...')
fig, ax = plt.subplots()
#ax.plot(pe, [(ndec[plt1]/float(n))*100 for plt1 in range(len(pe))], 'k--', label="Uncoded")
#ax.plot([np1+1 for np1 in range(n)], dectry, 'k-', label="Proposed")
ax.plot([np2+1 for np2 in range(n)], nfec, 'k-', label="FEC control")
ax.plot([np3+1 for np3 in range(n)], [4 for np4 in range(n)], 'k--', label="Ideal")
ax.legend(loc=0)
plt.axis([0, n, 0, 8])
plt.xscale('linear')
plt.yscale('linear')
plt.xlabel('Packet number')
plt.ylabel('N-K FEC bytes')
plt.grid(True)
print ('Saving...')
plt.savefig('sim-updater-FEC.jpg', bbox_inches='tight')