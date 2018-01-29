# Iteration of the best N-K values
def NK(p, parr):
    pmax = [0] * len(parr)
    pnk = [0] * len(parr)
    for index, psize in enumerate(parr):
        nkarr = [0] * 9
        for i in range(9):
            nk = (i+1)*2
            if psize >= 100:
                nkarr[i] = (float(psize)/(nk+psize)) * (1-NPDEP(p, (psize+nk), nk))
            else:
                nkarr[i] += (float(psize)/(nk+psize)) * (1-PDEP(p, (psize+nk), nk))
        pnk[index] = (nkarr.index(max(nkarr))+1)*2
        pmax[index] = max(nkarr)
    
    print pnk
    print pmax
    maximum = pmax.index(max(pmax))
    
    return parr[maximum], pnk[maximum]+2