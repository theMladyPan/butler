let recordButton = document.getElementById("recordButton");
let statusText = document.getElementById("status");

// Initialize MicRecorderToMp3 with settings
const Mp3Recorder = new MicRecorder({
    bitRate: 128 // 128 kbps for good quality-to-size balance
});

let isRecording = false;


var wavesurfer = WaveSurfer.create({
    container: '#waveform',
    waveColor: 'black',
    interact: false,
    cursorWidth: 0,
    plugins: [
        WaveSurfer.microphone.create()
    ]
});

// Handle record button click
recordButton.addEventListener("click", function () {
    if (!isRecording) {
        // Start microphone visualization
        wavesurfer.microphone.start();

        // Start recording
        Mp3Recorder.start()
            .then(() => {
                isRecording = true;
                recordButton.innerText = "Stop";
                statusText.innerText = "Recording...";
            })
            .catch(error => {
                console.error("Microphone access error:", error);
                statusText.innerText = "Microphone access denied.";
            });
    } else {
        // Stop recording
        Mp3Recorder.stop().getMp3()
            .then(([buffer, blob]) => {
                // Stop microphone visualization
                wavesurfer.microphone.stop();

                //generate random filename
                const random = Math.floor(Math.random() * 1000000);
                const filename = `recording_${random}.mp3`;
                // Upload the audio
                let formData = new FormData();
                formData.append("file", blob, filename);

                statusText.innerText = "Uploading...";
                fetch("/upload/record", { method: "POST", body: formData })
                    .then(response => response.json())
                    .then(result => {
                        if (result.url) {
                            statusText.innerHTML = `Upload complete! <a href="${result.url}" target="_blank">Listen here</a>`;
                        } else {
                            statusText.innerText = "Upload failed!";
                        }
                    })
                    .catch(error => {
                        console.error("Upload error:", error);
                        statusText.innerText = "Upload failed!";
                    });

                isRecording = false;
                recordButton.innerText = "Record";
            })
            .catch(error => {
                console.error("Recording error:", error);
                statusText.innerText = "Recording failed!";
                isRecording = false;
                recordButton.innerText = "Record";
            });
    }
});

// Handle microphone start/stop errors
wavesurfer.microphone.on("deviceError", function (code) {
    console.warn("Microphone error:", code);
    statusText.innerText = "Microphone error. Please check permissions.";
});
