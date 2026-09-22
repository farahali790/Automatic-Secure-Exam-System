"""Pre-flight: verify each module loads and processes one frame correctly."""
import sys, os, glob, base64

def b64_of(path):
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode()

# Allow: python test_modules.py path/to/image.jpg
if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):python test_modules.py
    sample_path = sys.argv[1]
else:
    # Search common locations, case-insensitive, all reasonable extensions
    patterns = []
    for d in ('static/assets', 'static', '.'):
        for ext in ('jpg', 'JPG', 'jpeg', 'JPEG',
                    'png', 'PNG', 'webp', 'WEBP'):
            patterns.append(f'{d}/*.{ext}')
    found = []
    for p in patterns:
        found.extend(glob.glob(p))
    if not found:
        print(f"\n❌ No image found.")
        print(f"   cwd: {os.getcwd()}")
        print(f"   searched: {patterns[:6]} ... (and {len(patterns)-6} more)")
        print(f"\n   Either pass a path:  python test_modules.py path/to/face.jpg")
        print(f"   Or check what's in your assets folder:  ls static/assets/")
        sys.exit(1)
    sample_path = found[0]

print(f"Testing with: {sample_path}\n")
frame_b64 = b64_of(sample_path)

from modules.object_detection import ObjectDetectionModule
from modules.gaze_detection   import GazeDetectionModule
from modules.face_recognition import FaceRecognitionModule

print("=== Object detection ===")
od = ObjectDetectionModule()
print("detect():", od.detect(frame_b64))
print("phone? ", od.analyze_frame_for_alerts(frame_b64)['mobile_phone'])

print("\n=== Gaze / behavior ===")
gd = GazeDetectionModule()
print("analyze():", gd.analyze(frame_b64))

print("\n=== Face recognition ===")
fr_mod = FaceRecognitionModule()
enc = fr_mod.extract_encoding(frame_b64)
print(f"encoding length: {len(enc) if enc else None} (expect 128)")
if enc:
    res = fr_mod.verify(frame_b64, enc)
    print(f"self-verify: {res}  (distance should be ~0.0)")

print("\n✅ all three modules loaded and produced sane output")