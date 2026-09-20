#include <chrono>
#include <cmath>
#include <cstdio>
#include <vector>
#include <complex>
static void fft(std::vector<std::complex<double>>& a, bool inv){
    size_t n=a.size(); if(n<=1)return;
    for(size_t i=1,j=0;i<n;i++){size_t b=n>>1;for(;j&b;b>>=1)j^=b;j^=b;if(i<j)std::swap(a[i],a[j]);}
    for(size_t len=2;len<=n;len<<=1){double ang=2*M_PI/double(len)*(inv?1:-1);std::complex<double> wl(std::cos(ang),std::sin(ang));
        for(size_t i=0;i<n;i+=len){std::complex<double> w(1);for(size_t j=0;j<len/2;j++){auto u=a[i+j],v=a[i+j+len/2]*w;a[i+j]=u+v;a[i+j+len/2]=u-v;w*=wl;}}}
    if(inv)for(auto&x:a)x/=double(n);
}
int main(){
    int n=16384, L=256; size_t nfft=1; while(nfft<size_t(2*n))nfft<<=1;
    std::vector<double> a(n),b(n); for(int i=0;i<n;i++){a[i]=std::sin(0.05*i);b[i]=std::sin(0.05*(i-21));}
    auto t0=std::chrono::steady_clock::now();
    volatile double sink=0;
    for(int r=0;r<20;r++){
        // naive xcorr
        std::vector<double> vals(2*L+1);
        for(int li=0;li<2*L+1;li++){int d=li-L;long long lo=std::max(0,-d),hi=std::min(n,n-d);
            double s=0;for(long long k=lo;k<hi;k++)s+=a[k]*b[k+d];vals[li]=s;}
        sink+=vals[L];
    }
    auto t1=std::chrono::steady_clock::now();
    for(int r=0;r<20;r++){
        std::vector<std::complex<double>> A(nfft),B(nfft);
        for(int i=0;i<n;i++){A[i]=a[i];B[i]=b[i];}
        fft(A,false);fft(B,false);
        for(size_t i=0;i<nfft;i++){auto R=A[i]*std::conj(B[i]);double m=std::abs(R)+1e-12;A[i]=R*std::pow(m,-0.35);}
        fft(A,true); sink+=A[100].real();
    }
    auto t2=std::chrono::steady_clock::now();
    printf("naive xcorr: %.2f ms/call\n", std::chrono::duration<double,std::milli>(t1-t0).count()/20);
    printf("gcc path   : %.2f ms/call\n", std::chrono::duration<double,std::milli>(t2-t1).count()/20);
    return 0;
}
