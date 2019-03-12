const dgram = require('dgram');
const server = dgram.createSocket('udp4');
var fs = require('fs');
server.on('message', (msg, _) => {
    fs.appendFileSync("log.txt",msg+"\n")
});


server.bind(9000);