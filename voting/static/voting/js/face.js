// Face capture and (optional) comparison using face-api.js
async function loadModels() {
    await faceapi.nets.tinyFaceDetector.loadFromUri('/static/models');
    await faceapi.nets.faceLandmark68Net.loadFromUri('/static/models');
    await faceapi.nets.faceRecognitionNet.loadFromUri('/static/models');
}

async function captureAndCompare() {
    const video = document.getElementById('video');
    const canvas = document.getElementById('canvas');
    const context = canvas.getContext('2d');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const detection = await faceapi.detectSingleFace(canvas, new faceapi.TinyFaceDetectorOptions())
                        .withFaceLandmarks().withFaceDescriptor();
    if (detection) {
        const descriptor = detection.descriptor;
        // Send descriptor to server for storage/comparison
        fetch('/api/face/compare/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ descriptor: descriptor })
        }).then(res => res.json()).then(data => {
            // handle result
        });
    }
}