function sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value;
    if (!message) return;
    // Display user message
    addMessage(message, 'user');
    input.value = '';
    // Send to server
    fetch('/chatbot/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ message: message })
    }).then(res => res.json()).then(data => {
        addMessage(data.response, 'bot');
    });
}
function addMessage(text, sender) {
    const chatBox = document.getElementById('chat-box');
    const div = document.createElement('div');
    div.classList.add('message', sender);
    div.textContent = text;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
}