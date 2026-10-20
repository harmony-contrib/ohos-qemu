/* Fixed read-only guest interface observations. No daemon or network mutation. */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <net/if.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <unistd.h>
static void need(int ok,const char *why){if(!ok){perror(why);exit(2);}}
int main(int argc,char **argv){
    need(argc==2 && strlen(argv[1])==32,"one fixed nonce");
    for(int i=0;i<32;++i)need((argv[1][i]>='0'&&argv[1][i]<='9')||(argv[1][i]>='a'&&argv[1][i]<='f'),"nonce chars");
    need(getuid()==0,"root observation fixture");int fd=socket(AF_INET,SOCK_DGRAM|SOCK_CLOEXEC,0);need(fd>=0,"read-only ioctl socket");
    for(int n=0;n<2;++n){const char *name=n?"eth1":"eth0";struct ifreq req={0};strncpy(req.ifr_name,name,IFNAMSIZ-1);
        need(ioctl(fd,SIOCGIFFLAGS,&req)==0,"actual Ethernet flags");unsigned flags=(unsigned short)req.ifr_flags;
        need(ioctl(fd,SIOCGIFHWADDR,&req)==0,"actual Ethernet MAC");unsigned char *a=(unsigned char*)req.ifr_hwaddr.sa_data;
        char mac[32];snprintf(mac,sizeof(mac),"%02x:%02x:%02x:%02x:%02x:%02x",a[0],a[1],a[2],a[3],a[4],a[5]);
        char address[INET_ADDRSTRLEN]="",mask[INET_ADDRSTRLEN]="";int ip_error=0;
        if(ioctl(fd,SIOCGIFADDR,&req)==0){need(inet_ntop(AF_INET,&((struct sockaddr_in*)&req.ifr_addr)->sin_addr,address,sizeof(address))!=NULL,"actual IPv4 text");
            need(ioctl(fd,SIOCGIFNETMASK,&req)==0,"actual IPv4 mask");need(inet_ntop(AF_INET,&((struct sockaddr_in*)&req.ifr_netmask)->sin_addr,mask,sizeof(mask))!=NULL,"actual mask text");
        }else{ip_error=errno;need(ip_error==EADDRNOTAVAIL,"actual absent IPv4 errno");}
        printf("{\"run_id\":\"%s\",\"uid\":%d,\"pid\":%d,\"interface\":\"%s\",\"ifindex\":%u,\"mac\":\"%s\",\"flags\":%u,\"address\":\"%s\",\"netmask\":\"%s\",\"address_errno\":%d}\n",argv[1],getuid(),getpid(),name,if_nametoindex(name),mac,flags,address,mask,ip_error);
    }need(close(fd)==0,"close observation socket");return 0;
}
