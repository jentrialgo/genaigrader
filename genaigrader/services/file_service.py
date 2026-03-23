import os


def save_uploaded_file(uploaded_file):
    file_path = os.path.join("uploaded_files", uploaded_file.name)
    with open(file_path, "wb") as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)
    return file_path
