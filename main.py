from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
import zipfile
import pydicom
import os
import matplotlib.pyplot as plt
import numpy as np
import shutil
from starlette.middleware.cors import CORSMiddleware

app = FastAPI()

# Cấu hình middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Hoặc cụ thể, ví dụ ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],  # Cho phép tất cả các phương thức HTTP
    allow_headers=["*"],  # Cho phép tất cả các header
)

# Cấu hình thư mục static và templates
TEMP_DIR = "temp_images"
os.makedirs(TEMP_DIR, exist_ok=True)
app.mount("/images", StaticFiles(directory=TEMP_DIR), name="images")  # Đảm bảo thư mục hình ảnh được phục vụ
templates = Jinja2Templates(directory="templates")

def process_dicom(dicom_path: str, output_dir: str) -> dict:
    """Xử lý file DICOM và lưu thành ảnh PNG"""
    try:
        dataset = pydicom.dcmread(dicom_path)
        
        info = {
            'filename': os.path.basename(dicom_path),
            'PatientName': str(dataset.PatientName) if hasattr(dataset, 'PatientName') else 'N/A',
            'PatientID': dataset.PatientID if hasattr(dataset, 'PatientID') else 'N/A',
            'StudyDate': dataset.StudyDate if hasattr(dataset, 'StudyDate') else 'N/A',
            'Modality': dataset.Modality if hasattr(dataset, 'Modality') else 'N/A'
        }
        
        if hasattr(dataset, 'pixel_array'):
            image_data = dataset.pixel_array
            image_data = (image_data - np.min(image_data)) / (np.max(image_data) - np.min(image_data))
            image_data = (image_data * 255).astype(np.uint8)
            
            png_filename = f"{os.path.splitext(info['filename'])[0]}.png"
            png_path = os.path.join(output_dir, png_filename)
            
            # Lưu ảnh PNG
            plt.imsave(png_path, image_data, cmap='gray')
            info['image_path'] = f"http://localhost:8000/images/{png_filename}"  # Đảm bảo trả về đường dẫn đến ảnh PNG
            
            return info
        return None
    except Exception as e:
        print(f"Lỗi xử lý file {dicom_path}: {str(e)}")
        return None

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        # Xóa các file cũ trong thư mục temp_images
        for filename in os.listdir(TEMP_DIR):
            file_path = os.path.join(TEMP_DIR, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f'Lỗi khi xóa file {file_path}: {e}')

        # Tạo thư mục tạm để giải nén file ZIP
        extract_dir = "temp_extract"
        os.makedirs(extract_dir, exist_ok=True)

        # Lưu và giải nén ZIP
        zip_path = os.path.join(extract_dir, file.filename)
        with open(zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        results = []
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
            
            for root, dirs, files in os.walk(extract_dir):
                for filename in files:
                    if filename.endswith('.dcm'):
                        dicom_path = os.path.join(root, filename)
                        result = process_dicom(dicom_path, TEMP_DIR)
                        if result:
                            results.append(result)

        # Dọn dẹp thư mục tạm
        shutil.rmtree(extract_dir)
        
        return {"results": results}  # Đảm bảo trả về đúng định dạng JSON
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
