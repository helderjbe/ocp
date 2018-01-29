import reedsolo
import random
import matplotlib
matplotlib.use("Pdf")
import matplotlib.pyplot as plt
import math

# Init
reedsolo.init_tables(0x11d)

# Probability of errors
#pe = [0.1, 0.25, 0.5, 0.75, 1]
pe = [0.001, 0.01, 0.03, 0.05, 0.1, 0.15, 0.25, 0.40, 0.5]
lpe=len(pe)+1
# Number of packets to test for each probability
n= 10000

dec=[0] * lpe
idec=[0] * lpe
terr=[0] * lpe
naks=[0] * lpe
narq=[0] * lpe
ndec=[0] * lpe
nsym=[0] * lpe
veff=[0] * lpe

p9=reedsolo.rs_encode_msg('1234'*2+'1', 18)
p65=reedsolo.rs_encode_msg('1234'*16+'1', 18)
p237=reedsolo.rs_encode_msg('1234'*59+'1', 18)
p=[]

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

# Simulation loop
for i, inum in enumerate(pe):
    print('Progress: %d/%d' % (i+1, len(pe)))
    
    if inum < 0.0179:
        p=p237
        veff[i]=237
    elif inum < 0.0596:
        p=p65
        veff[i]=65
    else:
        p=p9
        veff[i]=9
        
    nki = NK(inum, veff[i])
    print nki
    
    for j in range(n):
        nak_count=0
        en=[]
        nk=0
        nsym[i]+=nki
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
                    
            # Channel simulation
            if veff[i] == 237:
                nsym[i]+=237
            elif veff[i] == 65:
                nsym[i]+=65
            else:
                nsym[i]+=9
                
            for x,y in enumerate(en):
                # Add errors
                if random.random() < pe[i]:
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
                rs_packet=todec + ''.join('0' for x in range(18-nk))
                de = reedsolo.rs_correct_msg(rs_packet, 18, 0, 2, [rs for rs in range(len(todec),(len(todec)+(18-nk)))])[0]
                # Correct decoding?
                if de == p[:-18]:
                    dec[i]+=1
                else:
                    idec[i]+=1
                    
                break
            except (reedsolo.ReedSolomonError, ZeroDivisionError):
                nsym[i]+=5
                nak_count+=1
                if (nki + nak_count*2) > 18:
                    terr[i]+=1
                    break
                
                if nak_count == 1:
                    naks[i]+=1

# Get theoretical values
# Probabilities of decoding
seff_33 = [(1/3.0)*((1-PDEP(m1, 27, 18))*100) for kpe1,m1 in enumerate(pe)] + [0]
seff_50 = [(9.0/17)*((1-PDEP(m2, 18, 9))*100) for kpe2,m2 in enumerate(pe)] + [0]
seff_82 = [(9.0/11)*((1-PDEP(m3, 11, 2))*100) for kpe3,m3 in enumerate(pe)] + [0]

# Efficiency
seff = [(((float(veff[d])*dec[d])/nsym[d])*100) for d in range(len(nsym)-1)] + [0]
npow = [((float(nsym[npowk])/n)-veff[npowk]) for npowk in range(len(nsym)-1)] + [0]

# ndec - Uncoded number
# dec - Decoded number
# dect - Theoretical value
# idec - Incorrect decoding
# naks - Number of naks
# terr - Transmission failures

pe += [1]
# Plotting decoded packets
print ('Plotting...')
fig, ax = plt.subplots()
#ax.plot(pe, [(ndec[plt1]/float(n))*100 for plt1 in range(len(pe))], 'k--', label="Uncoded")
ax.plot(pe, [(dec[plt2]/float(n))*100 for plt2 in range(len(pe))], 'k-', label="Proposed")
ax.plot(pe, [([10000, 9949, 9554, 9010, 7017, 4911, 1958, 339, 62, 0][plt9]/float(10000))*100 for plt9 in range(len(pe))], 'k:', label="RS 9/11")
ax.plot(pe, [([10000, 10000, 10000, 9987, 9757, 9018, 5742, 1304, 237, 0][plt10]/float(10000))*100 for plt10 in range(len(pe))], 'k-.', label="RS 9/17")
ax.plot(pe, [([10000, 10000, 10000, 10000, 9999, 9949, 8851, 3070, 618, 0][plt11]/float(10000))*100 for plt11 in range(len(pe))], 'k--', label="RS 1/3")
ax.legend(loc=0)
plt.axis([pe[0], pe[-1], 0, 100])
plt.xscale('log')
plt.yscale('linear')
plt.xlabel('P(symbol error)')
plt.ylabel('Decoded packets (%)')
plt.grid(True)
print ('Saving...')
plt.savefig('sim-master-decode.jpg', bbox_inches='tight')

# Plotting
print ('Plotting...')
fig, ax = plt.subplots()
ax.plot(pe, [(naks[plt3]/float(n))*100 for plt3 in range(len(pe))], 'k-', label="Experimental")
#ax.legend(loc=0)
plt.axis([pe[0], pe[-1], 0, 100])
plt.xscale('log')
plt.yscale('linear')
plt.xlabel('P(symbol error)')
plt.ylabel('Retransmissions (%)')
plt.grid(True)
print ('Saving...')
plt.savefig('sim-master-naks.jpg', bbox_inches='tight')

# Plotting efficiency (real)
print ('Plotting...')
fig, ax = plt.subplots()
ax.plot(pe, seff, 'k-', label="Proposed")
ax.plot(pe, seff_82, 'k:', label="RS 9/11")
ax.plot(pe, seff_50, 'k-.', label="RS 9/17")
ax.plot(pe, seff_33, 'k--', label="RS 1/3")
ax.legend(loc=0)
plt.axis([pe[0], pe[-1], 0, 100])
plt.xscale('log')
plt.yscale('linear')
plt.xlabel('P(symbol error)')
plt.ylabel('Efficiency (%)')
plt.grid(True)
print ('Saving...')
plt.savefig('sim-master-efficiency.jpg', bbox_inches='tight')