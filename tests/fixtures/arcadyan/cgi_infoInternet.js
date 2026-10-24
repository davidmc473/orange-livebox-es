
var defroute_wan_ip="203.0.113.10";
var ipv6_info_buf="/";
addCfg("wan_defRoute", "65543000000", "0");
addCfg("dslx_dnsenable0", "65565001000", "1");
addCfg("dslx_dnsenable1", "65565002000", "1");
addCfg("dslx_dnsenable2", "65565003000", "");

addCfg("wan_dns", "393229000000", "62.36.225.150 62.37.228.20 192.168.1.1");
addCfg("ipv6_wan_dns1_0", "65684001000", "");
addCfg("ddns_service_0", "1179650001000", "dyndns");
addCfg("firewall_level", "983143000000", "1");
addCfg("firewall_enable", "655360000000", "1");
var wan_connTime='3600';
var wan_link_status=[['up','',''],null];
wan_connTime=(wan_connTime!="")?parseInt(wan_connTime):0;
var ipv6_wan_ip="0:0:0:0:0:0:0:0";
(function(){
var wan_ipv6_info=ipv6_info_buf.split("/");
if(ipv6_info_buf==""||wan_ipv6_info[0]==""||wan_ipv6_info[0]=="::"){
ipv6_wan_ip="0:0:0:0:0:0:0:0";}
else{
ipv6_wan_ip=wan_ipv6_info[0].toUpperCase();}})();
