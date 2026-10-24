var dhcp_enable='1';
var dhcp_startip='192.168.1.10';
var dhcp_endip='192.168.1.150';
var lan_mask='255.255.255.0';
var leasetime='1440';
var lan_ip='192.168.1.1';
var lan_mac_addr='60:8d:26:00:00:14';
var lan_status_list=[['1','up','1G','FD'],['2','up','100M','HD'],['3','down','0M','FD'],['4','up','1G','FD'],['5','up','2.5G','FD'],['6','down','0M','FD'],null];
var dhcp_leaseTime=[ 'laptop-test','192.168.1.20','02:00:00:00:00:01','13:49:16','LAN'
,'phone-test','192.168.1.21','02:00:00:00:00:02','18:40:09','LAN'
];
var dhcpv6_enable='';
var ipv6_gua='';
var ipv6_prefix='';
addCfg("LogName0", "393284001000", "LAN1");
addCfg("LogName1", "393284002000", "LAN2");
addCfg("LogName2", "393284003000", "LAN3");
addCfg("LogName3", "393284004000", "LAN4");
addCfg("LogName4", "393284005000", "2.5G LAN");
var lan_ports={};
var dhcp_client_num=0;
(function(){
var i=0,len=0,data=[];
if(typeof lan_status_list!='undefined')
{
len=lan_status_list.length;
for(i=0;i<len;i++){
var arr=lan_status_list[i];
if(arr){
data.push(arr[1],arr[2],((arr[3]=="FD")?"FULL":"HALF"));
lan_ports["lan"+arr[0]]=data;}}}
if(typeof dhcp_leaseTime!='undefined')
{
len=dhcp_leaseTime.length;
for(i=0;i<len;i+=5)dhcp_client_num++;}})();
