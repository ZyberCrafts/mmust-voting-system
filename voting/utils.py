# voting/utils.py

import hashlib
import base64
import logging
import json
import re
import requests
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP, AES
from Crypto.Util.Padding import pad, unpad
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from io import BytesIO
import cv2
import numpy as np
from .models import Election

logger = logging.getLogger(__name__)

def get_active_election():
    """Return the current active election or the latest closed one."""
    now = timezone.now()
    election = Election.objects.filter(start_time__lte=now, end_time__gte=now, is_active=True).first()
    if not election:
        election = Election.objects.filter(end_time__lt=now).order_by('-end_time').first()
    return election
# ------------------------------------------------------------------
# Cryptographic Utilities
# ------------------------------------------------------------------
def generate_key_pair():
    """Generate RSA key pair (2048-bit) for vote encryption."""
    try:
        key = RSA.generate(2048)
        private_key = key.export_key()
        public_key = key.publickey().export_key()
        return private_key, public_key
    except Exception as e:
        logger.error(f"Key pair generation failed: {e}")
        return None, None

def encrypt_vote(vote_data, public_key):
    """Encrypt vote data using RSA public key (OAEP padding)."""
    try:
        key = RSA.import_key(public_key)
        cipher = PKCS1_OAEP.new(key)
        if isinstance(vote_data, str):
            vote_data = vote_data.encode('utf-8')
        encrypted = cipher.encrypt(vote_data)
        return base64.b64encode(encrypted).decode('utf-8')
    except Exception as e:
        logger.error(f"Vote encryption failed: {e}")
        return None

def decrypt_vote(encrypted_vote, private_key):
    """Decrypt vote data using RSA private key."""
    try:
        key = RSA.import_key(private_key)
        cipher = PKCS1_OAEP.new(key)
        decrypted = cipher.decrypt(base64.b64decode(encrypted_vote))
        return decrypted.decode('utf-8')
    except Exception as e:
        logger.error(f"Vote decryption failed: {e}")
        return None

def encrypt_private_key(private_key, passphrase):
    """Encrypt private key with AES-256 for storage."""
    try:
        key = hashlib.sha256(passphrase.encode()).digest()
        cipher = AES.new(key, AES.MODE_CBC)
        ct_bytes = cipher.encrypt(pad(private_key, AES.block_size))
        iv = base64.b64encode(cipher.iv).decode('utf-8')
        ct = base64.b64encode(ct_bytes).decode('utf-8')
        return json.dumps({'iv': iv, 'ciphertext': ct})
    except Exception as e:
        logger.error(f"Private key encryption failed: {e}")
        return None

def decrypt_private_key(encrypted_data, passphrase):
    """Decrypt AES-encrypted private key."""
    try:
        data = json.loads(encrypted_data)
        iv = base64.b64decode(data['iv'])
        ct = base64.b64decode(data['ciphertext'])
        key = hashlib.sha256(passphrase.encode()).digest()
        cipher = AES.new(key, AES.MODE_CBC, iv)
        pt = unpad(cipher.decrypt(ct), AES.block_size)
        return pt
    except Exception as e:
        logger.error(f"Private key decryption failed: {e}")
        return None

def generate_receipt(encrypted_vote, user_id):
    """Generate unique receipt ID for vote verification."""
    data = f"{encrypted_vote}{user_id}{settings.SECRET_KEY}"
    return hashlib.sha256(data.encode()).hexdigest()

def generate_qr_code(data):
    """Generate QR code image from data and return base64 string."""
    import qrcode
    qr = qrcode.make(data)
    buffer = BytesIO()
    qr.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()

# ------------------------------------------------------------------
# Notification Utilities
# ------------------------------------------------------------------
def send_notification(user, subject, message, send_email=True, send_sms=False):
    """Send email and/or SMS to a user."""
    # Email
    if send_email and user.email:
        try:
            send_mail(
                subject,
                message,
                settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=False
            )
            logger.info(f"Email sent to {user.email}: {subject}")
        except Exception as e:
            logger.error(f"Email failed for {user.email}: {e}")

    # SMS via Africa's Talking (or other provider)
    if send_sms and user.phone:
        try:
            url = "https://api.africastalking.com/version1/messaging"
            headers = {
                "ApiKey": settings.SMS_API_KEY,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            data = {
                "username": settings.SMS_USERNAME,
                "to": user.phone,
                "message": message[:160]
            }
            response = requests.post(url, headers=headers, data=data, timeout=10)
            if response.status_code == 200:
                logger.info(f"SMS sent to {user.phone}")
            else:
                logger.error(f"SMS failed: {response.text}")
        except Exception as e:
            logger.error(f"SMS exception for {user.phone}: {e}")

# ------------------------------------------------------------------
# IP Geolocation
# ------------------------------------------------------------------
def get_ip_location(ip):
    """Return (latitude, longitude) for given IP using ipapi.co."""
    try:
        response = requests.get(f'https://ipapi.co/{ip}/json/', timeout=5)
        data = response.json()
        return data.get('latitude'), data.get('longitude')
    except Exception:
        return None, None

# ------------------------------------------------------------------
# Face Recognition Utilities (OpenCV + HOG)
# ------------------------------------------------------------------
def compute_hog_descriptor(face_img):
    """
    Compute HOG descriptor for a grayscale face image.
    Returns a 1D numpy array (histogram).
    """
    face_resized = cv2.resize(face_img, (128, 128))
    win_size = (128, 128)
    block_size = (16, 16)
    block_stride = (8, 8)
    cell_size = (8, 8)
    nbins = 9
    hog = cv2.HOGDescriptor(win_size, block_size, block_stride, cell_size, nbins)
    hog_features = hog.compute(face_resized)
    hog_features = hog_features.flatten()
    norm = np.linalg.norm(hog_features)
    if norm > 0:
        hog_features = hog_features / norm
    return hog_features

def extract_face_embedding(image_data):
    """
    Extract HOG embedding from face in image.
    Returns bytes of float32 array, or None if no face.
    """
    try:
        # Decode base64 or raw bytes
        if isinstance(image_data, str):
            if image_data.startswith('data:image'):
                image_data = image_data.split(',')[1]
            img_bytes = base64.b64decode(image_data)
        else:
            img_bytes = image_data

        np_arr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img is None:
            return None

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        face_cascade = cv2.CascadeClassifier(cascade_path)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))

        if len(faces) == 0:
            logger.warning("No face detected")
            return None

        # Use the largest face (by area)
        (x, y, w, h) = max(faces, key=lambda rect: rect[2] * rect[3])
        face_roi = gray[y:y+h, x:x+w]

        hog_features = compute_hog_descriptor(face_roi)
        return hog_features.astype(np.float32).tobytes()
    except Exception as e:
        logger.error(f"Face embedding extraction failed: {e}")
        return None

def store_face_embedding(user, image_data):
    """Extract and store face embedding for a user."""
    embedding = extract_face_embedding(image_data)
    if embedding:
        user.face_embedding = embedding
        user.save(update_fields=['face_embedding'])
        return True
    return False

def verify_face_with_distance(stored_embedding_bytes, selfie_data):
    """
    Returns (match: bool, distance: float)
    """
    try:
        if stored_embedding_bytes is None:
            return False, 1.0
        stored = np.frombuffer(stored_embedding_bytes, dtype=np.float32)
        new_embedding_bytes = extract_face_embedding(selfie_data)
        if new_embedding_bytes is None:
            return False, 1.0
        new_embed = np.frombuffer(new_embedding_bytes, dtype=np.float32)
        # Cosine similarity
        dot = np.dot(stored, new_embed)
        norm_stored = np.linalg.norm(stored)
        norm_new = np.linalg.norm(new_embed)
        if norm_stored == 0 or norm_new == 0:
            return False, 1.0
        similarity = dot / (norm_stored * norm_new)
        distance = 1 - similarity
        match = distance <= 0.35  # default tolerance
        return match, distance
    except Exception as e:
        logger.error(f"Face verification failed: {e}")
        return False, 1.0

def verify_face(stored_embedding_bytes, selfie_data, tolerance=0.35):
    """
    Compare stored embedding with new selfie.
    Returns True if match, else False.
    """
    match, distance = verify_face_with_distance(stored_embedding_bytes, selfie_data)
    logger.info(f"Face verification distance: {distance:.4f}, match: {match}")
    return match

def calibrate_face_tolerance(user, test_images):
    """
    Calibrate tolerance for a specific user by testing multiple selfies.
    test_images: list of base64 strings of the same person.
    Returns optimal tolerance (float).
    """
    if not user.face_embedding:
        return 0.35
    distances = []
    for img in test_images:
        _, distance = verify_face_with_distance(user.face_embedding, img)
        if distance is not None:
            distances.append(distance)
    if not distances:
        return 0.35
    mean_dist = np.mean(distances)
    std_dist = np.std(distances)
    tolerance = mean_dist + std_dist
    return min(max(tolerance, 0.25), 0.6)

# ------------------------------------------------------------------
# Candidate Eligibility (MMUST Portal Integration)
# ------------------------------------------------------------------
def check_candidate_eligibility(admission_number):
    from .portal_api import fetch_student_academic_status
    try:
        result = fetch_student_academic_status(admission_number)
        if result is None:
            logger.warning(f"Portal API returned None for {admission_number}")
            return None   # manual verification needed
        if result.get('missing_marks') or result.get('supplementary_exams'):
            return False
        return True
    except Exception as e:
        logger.error(f"Eligibility check failed: {e}")
        return None   # manual verification required

# ------------------------------------------------------------------
# Vote Tallying
# ------------------------------------------------------------------
def tally_votes(votes, private_key_pem):
    """
    Decrypt each vote and count results.
    Returns dict: {position_id: {candidate_id: count}}
    """
    tally = {}
    for vote in votes:
        decrypted = decrypt_vote(vote.encrypted_vote, private_key_pem)
        if decrypted:
            vote_data = json.loads(decrypted)
            for position_id, candidate_id in vote_data.items():
                if candidate_id is not None:
                    pos_id = int(position_id)
                    cand_id = int(candidate_id)
                    tally.setdefault(pos_id, {}).setdefault(cand_id, 0)
                    tally[pos_id][cand_id] += 1
    return tally

# ------------------------------------------------------------------
# Election Helpers
# ------------------------------------------------------------------
def get_election_public_key(election):
    """Retrieve public key from election (or generate if missing)."""
    if election.public_key:
        return election.public_key
    priv, pub = generate_key_pair()
    if priv and pub:
        election.public_key = pub
        master_pass = settings.ELECTION_MASTER_PASSPHRASE
        encrypted_priv = encrypt_private_key(priv, master_pass)
        election.private_key_encrypted = encrypted_priv
        election.save(update_fields=['public_key', 'private_key_encrypted'])
        return pub
    return None

# ------------------------------------------------------------------
# Data Validation
# ------------------------------------------------------------------
def validate_kenyan_phone(phone):
    """Return True if phone number is a valid Kenyan number."""
    pattern = r'^(?:\+254|0|1)[0-9]{9}$'
    return bool(re.match(pattern, phone))

def sanitize_input(text):
    """Basic XSS prevention (escaping)."""
    import html
    return html.escape(text.strip())

# ------------------------------------------------------------------
# Logging Helper
# ------------------------------------------------------------------
def log_audit(user, action, request=None, details=None):
    """Helper to create audit log entry (sync or async)."""
    from .models import AuditLog
    ip = None
    ua = None
    if request:
        ip = request.META.get('REMOTE_ADDR')
        ua = request.META.get('HTTP_USER_AGENT', '')
    AuditLog.objects.create(
        user=user,
        action=action,
        ip_address=ip,
        user_agent=ua,
        details=details or {}
    )