import os
import threading
import time
import shutil
import logging

from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    send_file,
    after_this_request
)
from flask_cors import CORS

# =====================================================
# Logging Configuration
# =====================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# =====================================================
# Flask App
# =====================================================

app = Flask(__name__)
CORS(app)

USB_DRIVE_LETTER = None
PORT = 8081

# =====================================================
# USB Detection
# =====================================================

def find_usb_drive():
    global USB_DRIVE_LETTER

    logging.info("Searching for USB drive...")

    while True:
        try:
            for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
                drive = f"{letter}:/"

                if os.path.isdir(drive):
                    USB_DRIVE_LETTER = letter
                    logging.info(f"USB detected at {drive}")
                    return

        except Exception as e:
            logging.exception(f"USB detection failed: {e}")

        time.sleep(2)

# =====================================================
# Request Logging
# =====================================================

@app.before_request
def log_request():
    logging.info(
        f"{request.remote_addr} "
        f"{request.method} "
        f"{request.path}"
    )

# =====================================================
# Routes
# =====================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/list")
def list_files():
    try:
        if not USB_DRIVE_LETTER:
            logging.warning("USB drive not detected")
            return jsonify([]), 404

        sub = request.args.get("path", "").strip("/")

        base = os.path.join(
            f"{USB_DRIVE_LETTER}:/",
            sub
        )

        logging.info(f"Listing: {base}")

        if not os.path.exists(base):
            return jsonify([])

        entries = [
            {
                "name": name,
                "is_folder": os.path.isdir(
                    os.path.join(base, name)
                )
            }
            for name in os.listdir(base)
        ]

        return jsonify(entries)

    except Exception as e:
        logging.exception("Error listing files")
        return jsonify({"error": str(e)}), 500


@app.route("/get_file")
def get_file():
    try:
        if not USB_DRIVE_LETTER:
            return "USB drive not detected", 404

        p = request.args.get("path", "").strip("/")

        full_path = os.path.join(
            f"{USB_DRIVE_LETTER}:/",
            p
        )

        logging.info("=" * 60)
        logging.info(f"Download Requested")
        logging.info(f"USB Drive: {USB_DRIVE_LETTER}")
        logging.info(f"Requested Path: {p}")
        logging.info(f"Full Path: {full_path}")
        logging.info(f"Exists: {os.path.exists(full_path)}")
        logging.info("=" * 60)

        if not os.path.exists(full_path):
            logging.error(f"File not found: {full_path}")
            return "File not found", 404

        return send_file(
            full_path,
            as_attachment=True,
            download_name=os.path.basename(full_path)
        )

    except Exception as e:
        logging.exception("Download failed")
        return str(e), 500


@app.route("/upload", methods=["POST"])
def upload_file():
    try:
        path = request.form.get("path", "").strip("/")
        file = request.files["file"]

        destination = os.path.join(
            f"{USB_DRIVE_LETTER}:/",
            path,
            file.filename
        )

        os.makedirs(
            os.path.dirname(destination),
            exist_ok=True
        )

        file.save(destination)

        logging.info(f"Uploaded: {destination}")

        return "OK"

    except Exception as e:
        logging.exception("Upload failed")
        return str(e), 500


@app.route("/mkdir", methods=["POST"])
def make_folder():
    try:
        data = request.json

        folder = os.path.join(
            f"{USB_DRIVE_LETTER}:/",
            data["path"].strip("/"),
            data["name"]
        )

        os.makedirs(folder, exist_ok=True)

        logging.info(f"Folder created: {folder}")

        return "OK"

    except Exception as e:
        logging.exception("Folder creation failed")
        return str(e), 500


@app.route("/touch", methods=["POST"])
def make_file():
    try:
        data = request.json

        file_path = os.path.join(
            f"{USB_DRIVE_LETTER}:/",
            data["path"].strip("/"),
            data["name"]
        )

        open(file_path, "w").close()

        logging.info(f"File created: {file_path}")

        return "OK"

    except Exception as e:
        logging.exception("File creation failed")
        return str(e), 500


@app.route("/delete", methods=["POST"])
def delete_item():
    try:
        data = request.json

        full_path = os.path.join(
            f"{USB_DRIVE_LETTER}:/",
            data["path"].strip("/")
        )

        if data.get("is_folder"):
            shutil.rmtree(full_path)
            logging.info(f"Folder deleted: {full_path}")
        else:
            os.remove(full_path)
            logging.info(f"File deleted: {full_path}")

        return "OK"

    except Exception as e:
        logging.exception("Delete failed")
        return str(e), 500


@app.route("/read_file")
def read_file():
    try:
        p = request.args.get("path", "").strip("/")

        file_path = os.path.join(
            f"{USB_DRIVE_LETTER}:/",
            p
        )

        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as file:
            return jsonify({
                "content": file.read()
            })

    except Exception as e:
        logging.exception("Read file failed")
        return str(e), 500


@app.route("/write_file", methods=["POST"])
def write_file():
    try:
        data = request.json

        file_path = os.path.join(
            f"{USB_DRIVE_LETTER}:/",
            data["path"].strip("/")
        )

        with open(
            file_path,
            "w",
            encoding="utf-8"
        ) as file:
            file.write(data["content"])

        logging.info(f"Updated file: {file_path}")

        return "OK"

    except Exception as e:
        logging.exception("Write file failed")
        return str(e), 500


@app.route("/health")
def health():
    return jsonify({
        "status": "running",
        "usb_drive": USB_DRIVE_LETTER,
        "port": PORT
    })


# =====================================================
# Remote Emulation Support Endpoints
# These endpoints are used by the Rutomatrix bridge.
# Existing upload/delete/edit/list behavior is unchanged.
# =====================================================

def _safe_usb_path(relative_path):
    if not USB_DRIVE_LETTER:
        raise RuntimeError("USB drive not detected")
    rel = (relative_path or "").replace('\\', '/').strip('/')
    root = os.path.abspath(f"{USB_DRIVE_LETTER}:/")
    full = os.path.abspath(os.path.join(root, rel))
    if os.path.commonpath([root, full]) != root:
        raise ValueError("Invalid path")
    return full


def _get_size_bytes(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for base, _, files in os.walk(path):
        for name in files:
            fp = os.path.join(base, name)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


@app.route("/item_info")
def item_info():
    try:
        p = request.args.get("path", "")
        full_path = _safe_usb_path(p)
        if not os.path.exists(full_path):
            return jsonify({"error": "Item not found"}), 404
        return jsonify({
            "name": os.path.basename(full_path.rstrip('/\\')),
            "is_folder": os.path.isdir(full_path),
            "size_bytes": _get_size_bytes(full_path)
        })
    except Exception as e:
        logging.exception("Item info failed")
        return jsonify({"error": str(e)}), 500


@app.route("/package_item")
def package_item():
    """Return the selected file/folder as a ZIP package for Rutomatrix."""
    import tempfile
    import zipfile

    try:
        p = request.args.get("path", "")
        full_path = _safe_usb_path(p)
        if not os.path.exists(full_path):
            return "Item not found", 404

        base_name = os.path.basename(full_path.rstrip('/\\')) or "usb_item"
        tmp = tempfile.NamedTemporaryFile(prefix="rutomatrix_pkg_", suffix=".zip", delete=False)
        tmp.close()

        with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
            if os.path.isfile(full_path):
                zf.write(full_path, arcname=base_name)
            else:
                for root_dir, _, files in os.walk(full_path):
                    rel_dir = os.path.relpath(root_dir, os.path.dirname(full_path))
                    if rel_dir == ".":
                        rel_dir = base_name
                    zf.writestr(rel_dir.rstrip('/') + '/', '')
                    for fname in files:
                        fp = os.path.join(root_dir, fname)
                        arc = os.path.join(rel_dir, fname)
                        zf.write(fp, arcname=arc)

        @after_this_request
        def cleanup(response):
            try:
                os.remove(tmp.name)
            except OSError:
                pass
            return response

        return send_file(
            tmp.name,
            as_attachment=True,
            download_name=f"{base_name}.zip",
            mimetype="application/zip"
        )
    except Exception as e:
        logging.exception("Package item failed")
        return str(e), 500

# =====================================================
# Main
# =====================================================

if __name__ == "__main__":
    logging.info("=" * 60)
    logging.info("USB FILE SERVER STARTING")
    logging.info(f"Port: {PORT}")
    logging.info("=" * 60)

    threading.Thread(
        target=find_usb_drive,
        daemon=True
    ).start()

    from waitress import serve

    logging.info(f"Listening on 0.0.0.0:{PORT}")

    serve(
        app,
        host="0.0.0.0",
        port=PORT
    )
 