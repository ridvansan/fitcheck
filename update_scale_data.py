import sys
import io
import json
import os
from datetime import datetime
import PIL.Image
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google import genai
from google.genai import types

class ScaleAutomator:
    def __init__(self, config_file='secrets.json', creds_file='google-creds.json', sheet_name='FitCheck_Reports'):
        # 1. Klasör yolunu belirle
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 2. Tam yolları (absolute path) oluştur
        self.config_path = os.path.join(self.base_dir, config_file)
        self.creds_path = os.path.join(self.base_dir, creds_file) 
        self.archive_dir = os.path.join(self.base_dir, 'archive/scale_results')
        
        self.sheet_name = sheet_name
        self.config = self._load_json(self.config_path)
        
        # 3. AI İstemcisi
        self.client = genai.Client(api_key=self.config.get("GEMINI_API_KEY"))
        self.model_id = self.config.get("MODEL_ID", "gemini-2.0-flash")
        
        # 4. Google Sheets Bağlantısı
        # Bu fonksiyon artık içeride self.creds_path kullanacak
        self.sheet = self._setup_sheets()
        
        if not os.path.exists(self.archive_dir):
            os.makedirs(self.archive_dir, exist_ok=True)

    def _setup_sheets(self):
        """Google Sheets API bağlantısını kurar."""
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        
        # Hata buradaydı: self.creds_file yerine self.creds_path kullanıyoruz
        creds = ServiceAccountCredentials.from_json_keyfile_name(self.creds_path, scope)
        client = gspread.authorize(creds)
        
        try:
            sh = client.open(self.sheet_name)
        except gspread.exceptions.SpreadsheetNotFound:
            sh = client.create(self.sheet_name)
            # secrets.json içindeki USER_EMAIL'i paylaş
            sh.share(self.config.get("USER_EMAIL"), perm_type='user', role='writer')
            ws = sh.get_worksheet(0)
            headers = ["Tarih", "Kilo", "BMI", "Yag_Kutlesi", "Vucut_Yagi", "Kas_Kutlesi", 
                       "Ic_Organ_Yaglanmasi", "Protein", "Yagsiz_Agirlik", "Vucut_Su_Orani", "BMR"]
            ws.append_row(headers)
        
        return sh.get_worksheet(0)

    def _load_json(self, file_name):
        with open(file_name, 'r') as f:
            return json.load(f)

    def _format_val(self, value):
        """Sayısal veriyi temizler."""
        if value is None: return ""
        return str(value).replace('kg', '').replace('%', '').replace('kcal', '').strip()

    def process_stream(self):
        """iPhone'dan gelen akışı işler ve Sheets'e yazar."""
        print("[*] iPhone'dan veri akışı alınıyor...")
        image_bytes = sys.stdin.buffer.read()
        
        if not image_bytes:
            return "[!] Hata: Boş veri akışı."

        img = PIL.Image.open(io.BytesIO(image_bytes))

        prompt = """
        Görseldeki verileri analiz et ve SADECE JSON döndür. 
        Anahtarlar: Tarih, Kilo, BMI, Yag_Kutlesi, Vucut_Yagi, Kas_Kutlesi, 
        Ic_Organ_Yaglanmasi, Protein, Yagsiz_Agirlik, Vucut_Su_Orani, BMR
        """

        try:
            # AI Analizi
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=[prompt, img],
                config=types.GenerateContentConfig(response_mime_type='application/json')
            )
            data = response.parsed if response.parsed else json.loads(response.text)
            
            # Google Sheets için satır hazırla (Sıralama önemli)
            row = [
                data.get("Tarih"),
                self._format_val(data.get("Kilo")),
                self._format_val(data.get("BMI")),
                self._format_val(data.get("Yag_Kutlesi")),
                self._format_val(data.get("Vucut_Yagi")),
                self._format_val(data.get("Kas_Kutlesi")),
                self._format_val(data.get("Ic_Organ_Yaglanmasi")),
                self._format_val(data.get("Protein")),
                self._format_val(data.get("Yagsiz_Agirlik")),
                self._format_val(data.get("Vucut_Su_Orani")),
                self._format_val(data.get("BMR"))
            ]
            
            # Sheets'e Ekle
            self.sheet.append_row(row)
            
            # Görseli Arşivle (Yedek olarak VM'de kalsın)
            self._archive_image(image_bytes, data.get("Tarih"))

            return f"[+] {data.get('Tarih')} verisi doğrudan Google Sheets'e eklendi."

        except Exception as e:
            return f"[!] Hata: {str(e)}"

    def _archive_image(self, image_bytes, date_str):
        clean_date = date_str.replace('/', '_')
        path = os.path.join(self.archive_dir, f"scale_{clean_date}.jpg")
        with open(path, 'wb') as f:
            f.write(image_bytes)

if __name__ == "__main__":
    assistant = ScaleAutomator()
    print(assistant.process_stream())