from flask import Flask, render_template, request, jsonify, send_from_directory, url_for
import os
from werkzeug.utils import secure_filename
from elevenlabs import ElevenLabs

import subprocess
import uuid

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['PROCESSED_FOLDER'] = 'processed'
app.config['ALLOWED_EXTENSIONS'] = {'mp3', 'wav', 'mp4', 'avi', 'mov', 'mkv'}

# Assurez-vous que les dossiers existent
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROCESSED_FOLDER'], exist_ok=True)

# Remplacez 'YOUR_API_KEY' par votre véritable clé API ElevenLabs
client = ElevenLabs(
    api_key="",
)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'Aucun fichier fourni'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Aucun fichier sélectionné'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_id = str(uuid.uuid4())
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], file_id + "_" + filename)
        file.save(upload_path)

        # Traitement du fichier
        file_extension = filename.rsplit('.', 1)[1].lower()
        if file_extension in {'mp4', 'avi', 'mov', 'mkv'}:
            # C'est un fichier vidéo
            # Extraire l'audio
            audio_filename = file_id + "_audio.wav"
            audio_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename)
            ffmpeg_extract_audio(upload_path, audio_path)

            # Isoler l'audio
            isolated_audio_path = os.path.join(app.config['PROCESSED_FOLDER'], file_id + "_isolated_audio.wav")
            isolate_audio(audio_path, isolated_audio_path)

            # Réintégrer l'audio dans la vidéo
            processed_video_path = os.path.join(app.config['PROCESSED_FOLDER'], file_id + "_processed_video.mp4")
            ffmpeg_combine_audio_video(upload_path, isolated_audio_path, processed_video_path)

            # Retourner le chemin du fichier vidéo traité
            return jsonify({'file_url': url_for('download_file', filename=os.path.basename(processed_video_path))})

        elif file_extension in {'mp3', 'wav'}:
            # C'est un fichier audio
            # Isoler l'audio
            isolated_audio_path = os.path.join(app.config['PROCESSED_FOLDER'], file_id + "_isolated_audio.wav")
            isolate_audio(upload_path, isolated_audio_path)

            # Retourner le chemin du fichier audio traité
            return jsonify({'file_url': url_for('download_file', filename=os.path.basename(isolated_audio_path))})

    else:
        return jsonify({'error': 'Type de fichier non autorisé'}), 400

@app.route('/process_link', methods=['POST'])
def process_link():
    data = request.get_json()
    link = data.get('link')
    if not link:
        return jsonify({'error': 'Aucun lien fourni'}), 400

    # Télécharger le média depuis le lien
    file_id = str(uuid.uuid4())
    download_path = os.path.join(app.config['UPLOAD_FOLDER'], file_id)
    os.makedirs(download_path, exist_ok=True)

    yt_dlp_download(link, download_path)

    # Trouver le fichier téléchargé
    download_file_path = None
    for root, dirs, files in os.walk(download_path):
        for file in files:
            download_file_path = os.path.join(root, file)
            break  # On prend le premier fichier trouvé

    if not download_file_path:
        return jsonify({'error': 'Échec du téléchargement du média'}), 400

    # Déterminer le type de fichier
    file_extension = download_file_path.rsplit('.', 1)[1].lower()
    if file_extension in {'mp4', 'avi', 'mov', 'mkv'}:
        # C'est un fichier vidéo
        # Extraire l'audio
        audio_filename = file_id + "_audio.wav"
        audio_path = os.path.join(app.config['UPLOAD_FOLDER'], audio_filename)
        ffmpeg_extract_audio(download_file_path, audio_path)

        # Isoler l'audio
        isolated_audio_path = os.path.join(app.config['PROCESSED_FOLDER'], file_id + "_isolated_audio.wav")
        isolate_audio(audio_path, isolated_audio_path)

        # Réintégrer l'audio dans la vidéo
        processed_video_path = os.path.join(app.config['PROCESSED_FOLDER'], file_id + "_processed_video.mp4")
        ffmpeg_combine_audio_video(download_file_path, isolated_audio_path, processed_video_path)

        # Retourner le chemin du fichier vidéo traité
        return jsonify({'file_url': url_for('download_file', filename=os.path.basename(processed_video_path))})

    elif file_extension in {'mp3', 'wav'}:
        # C'est un fichier audio
        # Isoler l'audio
        isolated_audio_path = os.path.join(app.config['PROCESSED_FOLDER'], file_id + "_isolated_audio.wav")
        isolate_audio(download_file_path, isolated_audio_path)

        # Retourner le chemin du fichier audio traité
        return jsonify({'file_url': url_for('download_file', filename=os.path.basename(isolated_audio_path))})

    else:
        return jsonify({'error': 'Type de fichier non pris en charge'}), 400

@app.route('/processed/<filename>')
def download_file(filename):
    return send_from_directory(app.config['PROCESSED_FOLDER'], filename)

def ffmpeg_extract_audio(video_path, audio_path):
    # Utiliser ffmpeg pour extraire l'audio de la vidéo
    command = [
        'ffmpeg', '-y', '-i', video_path, '-vn', '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2', audio_path
    ]
    subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def ffmpeg_combine_audio_video(video_path, audio_path, output_path):
    # Utiliser ffmpeg pour combiner la vidéo originale avec l'audio isolé
    command = [
        'ffmpeg', '-y', '-i', video_path, '-i', audio_path, '-c:v', 'copy', '-map', '0:v:0', '-map', '1:a:0', output_path
    ]
    subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def isolate_audio(input_audio_path, output_audio_path):
    # Utiliser l'API ElevenLabs pour isoler l'audio
    with open(input_audio_path, 'rb') as audio_file:
        audio_data = audio_file.read()
    audio = open(input_audio_path, 'rb')
    audio_stream = client.audio_isolation.audio_isolation_stream(audio=audio)

    #audio = File(file=audio_data, filename=os.path.basename(input_audio_path))
    #audio_stream = client.audio_isolation.audio_isolation_stream(audio=audio)

    # Écrire le flux audio isolé dans un fichier
    with open(output_audio_path, 'wb') as f:
        for chunk in audio_stream:
            f.write(chunk)

def yt_dlp_download(link, download_path):
    # Utiliser yt-dlp pour télécharger le média depuis le lien
    command = [
        'yt-dlp', '-o', os.path.join(download_path, '%(title)s.%(ext)s'), link
    ]
    subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

if __name__ == '__main__':
    app.run(debug=True)
