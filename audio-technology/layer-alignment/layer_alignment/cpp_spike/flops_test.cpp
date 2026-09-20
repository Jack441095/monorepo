#include <cstdio>
#include <chrono>
int main(){
    volatile double s=0; double x=1.0000001;
    auto t0=std::chrono::steady_clock::now();
    const long long N=100000000LL;
    for(long long i=0;i<N;i++) s+=x*2.0;
    auto t1=std::chrono::steady_clock::now();
    double sec=std::chrono::duration<double>(t1-t0).count();
    printf("scalar throughput: %.0f MFLOP/s (%.2fs for %lldM ops) sink=%g\n", N/sec/1e6, sec, N/1000000, (double)s);
    return 0;
}
