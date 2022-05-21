html = """
<!DOCTYPE html>
<html>
    <head>
        <title>Chat</title>
    </head>
    <body>
        <h1>WebSocket Chat</h1>
        <h2>Room ID: <span id="ws-room-id"></span></h2>
        <h2>Your ID: <span id="ws-id"></span></h2>
        <form action="" onsubmit="sendMessage(event)">
            <input type="text" id="roomText" autocomplete="off"/>
            <button onclick="connect(event)">Connect</button>
            <hr>
            <input type="text" id="messageText" autocomplete="off"/>
            <button>Send</button>

        </form>
        <ul id='messages'>
        </ul>
        <script>
            var client_id = Date.now()
            document.querySelector("#ws-id").textContent = client_id;
            var ws = null;

            function connect(event) {
                var room_id = document.getElementById('roomText').value;
                document.querySelector("#ws-room-id").textContent = room_id
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
                var input = document.getElementById("messageText")
                ws.send(input.value)
                input.value = ''
                event.preventDefault()
            }
            function close(event) {
                ws.send("client " + client_id + " closed chat ")
                ws.close()
            }
        </script>
    </body>
</html>
"""