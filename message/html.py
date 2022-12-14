html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Chat</title>
    </head>
    <body>
        <h1>WebSocket Chat</h1>
        <h2>Your Service: <span id="ws-service"></span></h2>
        <h2>Your ID: <span id="ws-id"></span></h2>
        <h2>Channel ID: <span id="ws-channel-id"></span></h2>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="serviceText" placeholder="service" autocomplete="off"/>
            <input type="text" id="userText" placeholder="user id" autocomplete="off"/>
            <input type="text" id="channelText" placeholder="channel id" autocomplete="off"/>
            <button onclick="connect(event)">Connect</button>
            <hr>
            <input type="text" id="messageText" autocomplete="off"/>
            <button>Send</button>

        </form>
        <ul id='messages'>
        </ul>
        <script>
            var ws = null;

            function connect(event) {
                var service = document.getElementById('serviceText').value;
                var user_id = document.getElementById('userText').value;
                var channel = document.getElementById('channelText').value;
                document.querySelector("#ws-service").textContent = service;
                document.querySelector("#ws-id").textContent = user_id;
                document.querySelector("#ws-channel-id").textContent = channel;
                ws = new WebSocket(`ws://localhost:8080/channels/${channel}/${service}/${user_id}`);
                ws.onmessage = function(event) {
                    var messages = document.getElementById('messages')
                    var message = document.createElement('li')
                    var content = document.createTextNode(event.data)
                    message.appendChild(content)
                    messages.appendChild(message)
                };
                event.preventDefault()
            }
            function sendMessage(event) {
                var message = document.getElementById("messageText");
                var service = document.getElementById("serviceText");
                var from = document.getElementById("userText");
                var date = Date.now();
                var msg = {
                    service: service.value,
                    from: from.value,
                    view_type: 'PLAINTEXT',
                    view: {
                        message: message.value,
                        source: {},
                        meta: {}
                    },
                    date: date  
                };
                ws.send(JSON.stringify(msg));
                message.value = '';
                event.preventDefault();
            }
            function close(event) {
                ws.send("client " + client_id + " closed chat ")
                ws.close()
            }
        </script>
    </body>
</html>
"""