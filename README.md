# gdown
### Download large files from Google Drive effortlessly.
![PyPI Version](https://img.shields.io/pypi/v/gdown.svg)
![Supported Python Versions](https://img.shields.io/pypi/pyversions/gdown.svg)
![CI](https://github.com/IAHispano/gdown/workflows/ci/badge.svg)

> [!IMPORTANT]  
Google's restrictions sometimes require using cookies for successful downloads. If direct access to a file is still possible via a browser, you can download the cookies file (`cookies.txt`) and place it in `~/.cache/gdown/cookies.txt`. Then re-run the download command.
>>


## 1. Description
Downloading large files from Google Drive can be tricky due to security measures. `gdown` simplifies this process, overcoming the limitations of traditional methods like `curl` or `wget`. It also supports downloading from Google Drive folders with a maximum of 50 files per folder.

## 2. Installation
```bash
pip install git+https://github.com/IAHispano/gdown

# to upgrade
pip install --upgrade git+https://github.com/IAHispano/gdown
```

## 3. Usage
### 1. From Command Line (CLI)
```bash
$ gdown --help

# Downloading a large file (~500MB)
$ gdown https://drive.google.com/uc?id=1l_5RK28JRL19wpT22B-DY9We3TVXnnQQ
$ md5sum fcn8s_from_caffe.npz
256c2a8235c1c65e62e48d3284fbd384

# Downloading a small file
$ gdown https://drive.google.com/uc?id=0B9P1L--7Wd2vU3VUVlFnbTgtS2c
$ cat spam.txt
spam

# Downloading a folder
$ gdown https://drive.google.com/drive/folders/15uNXeRBIhVvZJIhL4yTw4IsStMhUaaxl -O /tmp/folder --folder

# Downloading with alternative methods
$ gdown https://httpbin.org/ip -O ip.json
$ cat ip.json
{
  "origin": "126.169.213.247"
}
```

### 2. From Python
```python
import gdown

# Downloading a file
url = "https://drive.google.com/uc?id=1l_5RK28JRL19wpT22B-DY9We3TVXnnQQ"
output = "fcn8s_from_caffe.npz"
gdown.download(url, output, quiet=False)

# Downloading a folder
url = "https://drive.google.com/drive/folders/15uNXeRBIhVvZJIhL4yTw4IsStMhUaaxl"
gdown.download_folder(url, quiet=True, use_cookies=False)
```

## 4. Credits
All credits go to wkentaro.

## 5. License
See [LICENSE](LICENSE).
