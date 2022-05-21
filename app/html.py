html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Chat</title>
    </head>
    <body>
        <h1>WebSocket Chat</h1>
        <h2>Your ID: <span id="ws-id"></span></h2>
        <h2>Room ID: <span id="ws-room-id"></span></h2>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="userText" placeholder="user id" autocomplete="off"/>
            <input type="text" id="roomText" placeholder="room id" autocomplete="off"/>
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
                var client_id = document.getElementById('userText').value;
                var room_id = document.getElementById('roomText').value;
                document.querySelector("#ws-id").textContent = client_id;
                document.querySelector("#ws-room-id").textContent = room_id;
                ws = new WebSocket(`ws://localhost/chat/${client_id}/${room_id}`);
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
                var from = document.getElementById("userText");
                var date = Date.now();
                var msg = {
                    from: from.value,
                    message: message.value,
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