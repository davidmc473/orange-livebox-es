
addCfg("client_hostname0", "983253001000", "L%C3%A1mpara%20sal%C3%B3n");
addCfg("client_hostname1", "983253002000", "name unavailable");
addCfg("client_hostname2", "983253003000", "");
addCfg("client_mac0", "983254001000", "02:00:00:00:00:05");
addCfg("client_mac1", "983254002000", "02:00:00:00:00:01");
addCfg("client_mac2", "983254003000", "");
addCfg("client_deviceType0", "983255001000", "lightbulb");
addCfg("client_deviceType1", "983255002000", "");
addCfg("client_deviceType2", "983255003000", "");
addCfg("wl_enable24G", "196637000000", "1");
addCfg("wl_enable5G", "196701000000", "1");
function set_client_host(list)
{
var i=0
var j=0,len=list.length;
var mac;
for(i=0;i<ARC_DEF_LAN_CLIENT_MAXNUM;i++){
if(mac=="")
continue;
for(j=0;j<len;j++){
if((list[j].mac==mac)||(list[j].mac_from_dhcp_lease_file==mac)){
break;}}}}
var dhcp_client=[ 'laptop-test','192.168.1.20','02:00:00:00:00:01','','LAN'
,'phone-test','192.168.1.21','02:00:00:00:00:02','','LAN'
,'tv-dhcp-name','192.168.1.23','02:00:00:00:00:04','','LAN'
];
var online_client=[ ['laptop-test','192.168.1.20','02:00:00:00:00:01','0','LAN','0','fe80::1','0','DHCP','Online','','MSFT 5.0','2026/10/24 10:00:00','3600','eth3.0','00:00:00:00:00:00','02:00:00:00:00:01','','1000'],['phone-test','192.168.1.21','02:00:00:00:00:02','0','LAN','2001:db8::21','0','0','DHCP','Online','','android-dhcp-14','2026/10/24 11:00:00','120','eth3.0','00:00:00:00:00:00','02:00:00:00:00:02','','1000'],['old-name','192.168.1.22','02:00:00:00:00:03','0','LAN','0','0','0','Static','Offline','','','2025/01/01 10:00:00','10','eth3.0','00:00:00:00:00:00','00:00:00:00:00:00','','1000'],['new-name','192.168.1.22','02:00:00:00:00:03','0','LAN','0','0','0','DHCP','Online','','','2026/10/24 09:00:00','50','eth3.0','00:00:00:00:00:00','02:00:00:00:00:03','','100'],['','192.168.1.23','02:00:00:00:00:04','0','LAN','0','0','0','DHCP','Offline','','','2026/09/01 08:00:00','600','eth0.0','00:00:00:00:00:00','02:00:00:00:00:04','','0'],['','192.168.1.24','02:00:00:00:00:05','0','24G','0','0','0','DHCP','Online','','','2026/10/24 08:00:00','7200','eth3.0','00:00:00:00:00:00','02:00:00:00:00:05','Bombilla','0'],['broken','192.168.1.99','not-a-mac','0','LAN','0','0','0','DHCP','Online','','','','0','eth3.0','00:00:00:00:00:00','','','0']];
var client_list=[];
var List_Name=0,List_IP4=1,List_MAC=2,List_From=4;
(function(){
var list=[],idx=0,obj={},cfg_mac="";
var newAttr=function(){
this.mac="";
this.name="name unavailable";};
client_list=list;})();
var connType_displayStr=["LAN","2.4G"];
connType_displayStr.push("5G");
function isWireless(str){
if(str=="LAN")
return 0;
else if(str=="24G")
return 1;
else
return-1;}
var topology_info={ "nodes": [ { "hw_ver": "ARLTLBFIB61.0.0", "sn": "ARLT00TEST01", "device_mac": "60:8D:26:00:00:17", "device_id": "60:8D:26:00:00:17", "parent_id": "NULL", "device_name": "Livebox", "device_ip": "192.168.1.1", "essid_2g": "Livebox6-TEST", "sta_num": "4" } ], "cksum": "0" };
var station_info={"stations":[{"station_mac":"02:00:00:00:00:02","station_name":"phone-test","alias_name":"NULL","station_ip":"192.168.1.21","connect_type":"2.4G","link_rate":"54Mbps","signal_strength":"-80","online":"0","connect_ssid":"Livebox6-TEST"},{"station_mac":"02:00:00:00:00:02","station_name":"phone-test","alias_name":"NULL","station_ip":"192.168.1.21","connect_type":"5G","link_rate":"866Mbps","signal_strength":"-55","online":"1","connect_ssid":"Livebox6-TEST"},{"station_mac":"02:00:00:00:00:01","station_name":"laptop-test","station_ip":"192.168.1.20","connect_type":"Ether","link_rate":"1000Mbps","signal_strength":"0","online":"1","connect_ssid":"NULL"},{"station_mac":"02:00:00:00:00:06","station_name":"unknown_02:00:00:00:00:06","station_ip":"192.168.1.26","connect_type":"2.4G","link_rate":"72Mbps","signal_strength":"-70","online":"1","connect_ssid":"Livebox6-TEST"}]};
var system_uptime=86400.34;
