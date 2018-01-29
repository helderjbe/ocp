import reedsolo
import random
import matplotlib
matplotlib.use("Pdf")
import matplotlib.pyplot as plt

# Factorial of a number
def factorial(n):return reduce(lambda x,y:x*y,[1]+range(1,n+1))

# Calculation of packet decoding probability
def PDP(p, N, nk):
    min = (nk/2)+1
    pdp=0
    for k in range(min, N+1):
        # Calculate PDP with the formula from literature
        pdp += (float(factorial(N))/(factorial(k)*factorial(N-k)))*(p**k)*((1-p)**(N-k))
    
    return 1-pdp

# Init
reedsolo.init_tables(0x11d)

# Probability of errors
#pe = [0.1, 0.25, 0.5, 0.75, 1]
pe = [0.001, 0.01, 0.03, 0.05, 0.1, 0.15, 0.25, 0.40, 0.5]
petrace=pe+[1]
# Number of packets to test for each probability
n= 10000

#nkarr= [2]
nkarr= [2,8,18]

for nfig in range(len(nkarr)):
    # Packet to be tested
    nk=nkarr[nfig]
    packet=reedsolo.rs_encode_msg('123456789', nk)
    #packet=reedsolo.rs_encode_msg('1', nk)
    l=len(packet)

    dec=[0] * (len(pe)+1)
    ndec=[0] * (len(pe)+1)
    idec=[0] * (len(pe)+1)
    
    # Simulation loop
    for i, inum in enumerate(pe):
        print('Progress: %d/%d' % (i+1, len(pe)))
        for j in range(n):
            en = packet[:]
            # Channel simulation
            for x,y in enumerate(en):
                # Add errors based on probability to be tested
                if random.random() < pe[i]:
                    # Avoid writing a symbol that is the same as the original
                    if en[x]!=1:
                        en[x]=1
                    else:
                        en[x]=0
            
            if en[:-nk] == packet[:-nk]:
                ndec[i]+=1
                
            # Test if decodable
            try:
                de = reedsolo.rs_correct_msg(en, nk)[0]
                # Correct decoding?
                if de == packet[:-nk]:
                    dec[i]+=1
                else:
                    idec[i]+=1
            except reedsolo.ReedSolomonError:
                continue
    
    # Get theoretical values
    # Probabilities of decoding
    pt = [PDP(m, l, nk) for y,m in enumerate(pe)]
    # Multiply by packets
    dect= [a*n for y,a in enumerate(pt)] + [0]
    
    # ndec - Uncoded number
    # dec - Decoded number
    # dect - Theoretical value
    # idec - Incorrect decoding
    print dec
    
    # Plotting 1
    print ('Plotting...')
    fig, ax = plt.subplots()
    ax.plot(petrace, [(ndec[plt1]/float(n))*100 for plt1 in range(len(petrace))], 'k--', label="Uncoded")
    ax.plot(petrace, [(dect[plt2]/float(n))*100 for plt2 in range(len(petrace))], 'k:', label="Theory")
    ax.plot(petrace, [(dec[plt3]/float(n))*100 for plt3 in range(len(petrace))], 'kx', label="Experimental")
    ax.legend(loc=0)
    plt.axis([petrace[0],petrace[-1] , 0, 100])
    plt.xscale('log')
    plt.yscale('linear')
    plt.xlabel('P(symbol error)')
    plt.ylabel('Decoded packets (%)')
    plt.grid(True)
    print ('Saving...')
    plt.savefig(('sim-rs-%d.jpg' % nfig), bbox_inches='tight')
    #plt.savefig(('sim-rs-header-arq-%d.jpg' % nfig), bbox_inches='tight')
    
    # Plotting 1
    print ('Plotting...')
    fig, ax = plt.subplots()
    ax.plot(petrace, [(idec[plt4]/float(n))*100 for plt4 in range(len(petrace))], 'k-', label="Inc decodings")
    plt.axis([petrace[0], petrace[-1], 0, 20])
    plt.xscale('log')
    plt.yscale('linear')
    plt.xlabel('P(symbol error)')
    plt.ylabel('Undetected errors (%)')
    plt.grid(True)
    print ('Saving...')
    plt.savefig(('sim-rs-%d-inc.jpg' % nfig), bbox_inches='tight')
    #plt.savefig(('sim-rs-%d-header-arq-inc.jpg' % nfig), bbox_inches='tight')
	
'''
MatPlotLib
Copyright (c) 2012-2013 Matplotlib Development Team; All Rights Reserved
'''