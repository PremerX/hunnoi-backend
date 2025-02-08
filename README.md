<div align="center">
  <img src="https://github.com/user-attachments/assets/ba02218c-8524-40d3-bd94-633f8261da45" alt="cut-svgrepo-com" width="100" height="100">
  <h1 align="center"> 
    HUNNOI By PremerX.
  </h1>
</div>


**Hunnoi** is a free YouTube Playlist converter and downloader service for 1-2 hours long to MP3 files. It also divides songs in long Playlists into individual music files, making it easier to skip songs and go back to the previous song.

## Installation

This project can be installed in two ways:

### Method 1: Clone from Repository
Clone the repository using the following commands:

```bash
git clone https://github.com/PremerX/hunnoi-backend.git
cd hunnoi-backend
pip install -r requirements.txt
```

### Method 2: Pull from Docker
You can pull the pre-built Docker image using:
```bash
docker pull premerxdr/hunnoi-backend:latest
```

## Usage

### If Installed by Cloning the Repository
After cloning the repository, run the application with:
```bash
cd hunnoi-backend
uvicorn app.main:app
```
### If Pulled from Docker
If you pulled the Docker image, run a container using:
```bash
docker run -d \
  -p 8000:8000 \
  -e TZ="Asia/Bangkok" \
  --name hunnoi_backend \
  premerxdr/hunnoi-backend:latest
```
## Contributing

Pull requests are welcome. For major changes, please open an issue first
to discuss what you would like to change.

Please make sure to update tests as appropriate.
