import math
def wil(k,n,z=1.96):
    if not n: return '-'
    p=k/n; d=1+z*z/n; c=p+z*z/(2*n); r=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))
    return f"{(c+r)/d:.1%}"
