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
    def __init__(self, config_file='secrets.json', creds_file='google-creds.json', sheet_name='Scale_Reports'):
        # 1. Klasör ve Dosya Yolları (Absolute Path)
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(self.base_dir, config_file)
        self.creds_path = os.path.join(self.base_dir, creds_file)
        self.archive_dir = os.path.join(self.base_dir, 'archive/scale_results')
        
        self.config = self._load_json(self.config_path)
        
        # 2. Gemini 2.5 Flash ve API Ayarları
        self.client = genai.Client(api_key=self.config.get("GEMINI_API_KEY"))
        # Model ID doğrudan 2.5-flash olarak güncellendi
        self.model_id = self.config.get("MODEL_ID", "gemini-2.5-flash")
        
        self.sheet_name = sheet_name
        self.sheet = self._setup_sheets()
        
        if not os.path.exists(self.archive_dir):
            os.makedirs(self.archive_dir, exist_ok=True)

    def _load_json(self, file_name):
        with open(file_name, 'r') as f:
            return json.load(f)

    def _setup_sheets(self):
        """Google Sheets bağlantısını kurar ve yetkilendirir."""
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(self.creds_path, scope)
        client = gspread.authorize(creds)
        
        try:
            sh = client.open(self.sheet_name)
        except gspread.exceptions.SpreadsheetNotFound:
            # Belirtilen isimde (Scale_Reports) tablo yoksa oluşturur
            sh = client.create(self.sheet_name)
            sh.share(self.config.get("USER_EMAIL"), perm_type='user', role='writer')
            ws = sh.get_worksheet(0)
            headers = ["Tarih", "Kilo", "BMI", "Yag_Kutlesi", "Vucut_Yagi", "Kas_Kutlesi", 
                       "Ic_Organ_Yaglanmasi", "Protein", "Yagsiz_Agirlik", "Vucut_Su_Orani", "BMR"]
            ws.append_row(headers)
        
        return sh.get_worksheet(0)

    def _format_date(self, date_str):
        """Tarihi DD/MM/YYYY formatına zorlar ve saati eler."""
        try:
            raw_date = str(date_str).split(' ')[0]
            clean_date = raw_date.replace('.', '/').replace('-', '/')
            dt = datetime.strptime(clean_date, "%d/%m/%Y")
            return dt.strftime("%d/%m/%Y")
        except:
            return datetime.now().strftime("%d/%m/%Y")

    def _format_num(self, value):
        """Sayıları Türkiye yerel ayarına (virgül) uygun hale getirir."""
        if value is None: return ""
        s_val = str(value).replace('kg', '').replace('%', '').replace('kcal', '').strip()
        # Noktayı virgüle çevirerek Sheets'in sayı olarak tanımasını sağlar
        temp_val = s_val.replace(',', '.')
        return temp_val.replace('.', ',')

    def process_stream(self):
        """iPhone'dan gelen veriyi Gemini 2.5 ile işler."""
        image_bytes = sys.stdin.buffer.read()
        if not image_bytes: return "[!] Hata: Boş veri akışı."

        img = PIL.Image.open(io.BytesIO(image_bytes))

        prompt = """
        Görseldeki tartı verilerini analiz et ve SADECE JSON döndür. 
        KURAL: 'Tarih' alanında saat verme, sadece Gün/Ay/Yıl formatını kullan.
        Değerler: Kilo, BMI, Yag_Kutlesi, Vucut_Yagi, Kas_Kutlesi, Ic_Organ_Yaglanmasi, Protein, Yagsiz_Agirlik, Vucut_Su_Orani, BMR
        """.format(today=datetime.now().strftime("%d/%m/%Y"))

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=[prompt, img],
                config=types.GenerateContentConfig(response_mime_type='application/json')
            )
            data = response.parsed if response.parsed else json.loads(response.text)
            
            final_date = self._format_date(data.get("Tarih"))
            
            row = [
                final_date,
                self._format_num(data.get("Kilo")),
                self._format_num(data.get("BMI")),
                self._format_num(data.get("Yag_Kutlesi")),
                self._format_num(data.get("Vucut_Yagi")),
                self._format_num(data.get("Kas_Kutlesi")),
                self._format_num(data.get("Ic_Organ_Yaglanmasi")),
                self._format_num(data.get("Protein")),
                self._format_num(data.get("Yagsiz_Agirlik")),
                self._format_num(data.get("Vucut_Su_Orani")),
                self._format_num(data.get("BMR"))
            ]
            
            # Veriyi 'Kullanıcı yazmış gibi' ekleyerek otomatik tip dönüşümü yap
            self.sheet.append_row(row, value_input_option='USER_ENTERED')
            
            self._archive_image(image_bytes, final_date)
            return f"[+] {final_date} verisi Gemini 2.5 ile 'Scale_Reports' tablosuna eklendi."

        except Exception as e:
            return f"[!] Hata: {str(e)}"

    def _archive_image(self, image_bytes, date_str):
        clean_date = date_str.replace('/', '_')
        ts = datetime.now().strftime("%H%M%S")
        path = os.path.join(self.archive_dir, f"scale_{clean_date}_{ts}.jpg")
        with open(path, 'wb') as f:
            f.write(image_bytes)

if __name__ == "__main__":
    assistant = ScaleAutomator()
    print(assistant.process_stream())