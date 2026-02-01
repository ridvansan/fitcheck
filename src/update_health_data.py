import json
import os
import csv
import glob
import shutil
import PIL.Image
from google import genai
from google.genai import types

class ScaleAutomator:
    def __init__(self, secret_file='secrets.json', csv_file='scale_reports.csv'):
        self.secret_file = secret_file
        self.csv_file = csv_file
        self.archive_dir = 'archive/scale_results'
        self.api_key = self._load_api_key()
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None
        
        if not os.path.exists(self.archive_dir):
            os.makedirs(self.archive_dir)

    def _load_api_key(self):
        try:
            with open(self.secret_file, 'r') as f:
                return json.load(f).get("GEMINI_API_KEY")
        except Exception:
            return None

    def get_latest_airdrop_image(self):
        path = os.path.expanduser("~/Downloads")
        patterns = [
            "IMG_*.[jJ][pP][eE][gG]", "IMG-*.[jJ][pP][eE][gG]",
            "IMG_*.[jJ][pP][gG]", "IMG-*.[jJ][pP][gG]",
            "IMG_*.[pP][nN][gG]", "IMG-*.[pP][nN][gG]"
        ]
        files = []
        for p in patterns:
            files.extend(glob.glob(os.path.join(path, p)))
        return max(files, key=os.path.getctime) if files else None

    def _format_num(self, value):
        if value is None: return ""
        # Birimleri temizle ve ondalık ayracı olarak virgül kullan
        s_val = str(value).replace('kg', '').replace('%', '').replace('kcal', '').strip()
        return s_val.replace('.', ',')

    def process_and_archive(self):
        if not self.client: return "[!] API anahtarı hatası."
        
        image_path = self.get_latest_airdrop_image()
        if not image_path: return "[!] Yeni görsel bulunamadı."

        print(f"[*] İşleniyor: {os.path.basename(image_path)}")
        img = PIL.Image.open(image_path)

        # Prompt'a BMI eklendi
        prompt = """
        Görseldeki verileri analiz et ve SADECE JSON döndür. 
        - Tarih: Gün/Ay/Yıl formatında (Örn: 31/01/2026)
        - Kilo: Ana ağırlık
        - BMI: Vücut Kitle Endeksi (VKI)
        - Yag_Kutlesi: Fat Mass
        - Vucut_Yagi: Body Fat Percentage
        - Kas_Kutlesi: Muscle mass
        - Ic_Organ_Yaglanmasi: Visceral fat rating
        - Protein: Protein percentage
        - Yagsiz_Agirlik: Fat free body weight
        - Vucut_Su_Orani: Body water percentage
        - BMR: Basal metabolic rate
        """

        try:
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[prompt, img],
                config=types.GenerateContentConfig(response_mime_type='application/json')
            )
            data = response.parsed if response.parsed else json.loads(response.text)
            
            # CSV Verisini Hazırla (BMI dahil edildi)
            row = {
                "Tarih": data.get("Tarih"),
                "Kilo (kg)": self._format_num(data.get("Kilo")),
                "BMI": self._format_num(data.get("BMI")),
                "Yağ Kütlesi (kg)": self._format_num(data.get("Yag_Kutlesi")),
                "Vücut Yağı (%)": self._format_num(data.get("Vucut_Yagi")),
                "Kas Kütlesi (kg)": self._format_num(data.get("Kas_Kutlesi")),
                "İç Organ Yağlanması": self._format_num(data.get("Ic_Organ_Yaglanmasi")),
                "Protein (%)": self._format_num(data.get("Protein")),
                "Yağsız Ağırlık (kg)": self._format_num(data.get("Yagsiz_Agirlik")),
                "Vücut Su Oranı (%)": self._format_num(data.get("Vucut_Su_Orani")),
                "BMR (kcal)": self._format_num(data.get("BMR"))
            }
            self._update_csv(row)

            # Dosyayı Arşivle
            date_str = data.get("Tarih").replace('/', '_')
            extension = os.path.splitext(image_path)[1]
            new_filename = f"scale_{date_str}{extension}"
            
            dest_path = os.path.join(self.archive_dir, new_filename)
            shutil.move(image_path, dest_path)
            
            return f"[+] {data.get('Tarih')} verisi (BMI dahil) kaydedildi ve '{new_filename}' olarak arşivlendi."
        except Exception as e:
            return f"[!] Hata: {str(e)}"

    def _update_csv(self, row):
        file_exists = os.path.isfile(self.csv_file)
        # Yeni bir sütun (BMI) eklendiği için dosya varsa başlıkları kontrol etmek gerekebilir.
        # Eğer CSV halihazırda eskiyse, başlıkların güncellenmesi için dosyayı silip bir kez baştan çalıştırmak temiz sonuç verir.
        with open(self.csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=row.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

if __name__ == "__main__":
    assistant = ScaleAutomator()
    print(assistant.process_and_archive())