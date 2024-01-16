from flask import Flask, jsonify, request, send_file
from functools import wraps
from flask_cors import CORS, cross_origin
import os
import re
from operator import attrgetter
import numpy as np
from google.cloud import vision
import io
import unicodedata
import json
from datetime import datetime
from flask_swagger_ui import get_swaggerui_blueprint
from flasgger import Swagger
from gevent.pywsgi import WSGIServer
import base64
import pdf2image
from gevent import socket

socket.socket = socket.socket

template = {
  "swagger": "2.0",
  "info": {
    "title": "OCR",
    "description": "API for OCR KTP",
    "version": "0.1.0"
  },  
  "basePath": "/ocr", 
  "specs_route": "/ocr/apidocs/",
  "operationId": "getmyData"
}

'''swagger specific'''
SWAGGER_URL = "/ocr/swagger"
API_URL = './swagger.json'
SWAGGERUI_BLUEPRINT = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "OCR Indonesian Identity Card from PDF"
    }
)

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] ='cloud_vision.json'

app = Flask('__name__')
app.register_blueprint(SWAGGERUI_BLUEPRINT, url_prefix=SWAGGER_URL)
CORS(app)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')

        if token and token == 'Bearer VGVtYW4tTmVsYXlhbg':
            return f(*args, **kwargs)

        return jsonify({"status": 401, 
                        "data": {"timestamp": ts }, 
                        "message": "Invalid Token", 
                        "success": "false" }), 401

    return decorated
class ExtendedAnnotation:
    def __init__(self, annotation):
        self.vertex = annotation.bounding_poly.vertices
        self.text = annotation.description
        self.avg_y = (self.vertex[0].y + self.vertex[1].y + self.vertex[2].y + self.vertex[3].y) / 4
        self.height = ((self.vertex[3].y - self.vertex[1].y) + (self.vertex[2].y - self.vertex[0].y)) / 2
        self.start_x = (self.vertex[0].x + self.vertex[3].x) / 2

    def __repr__(self):
        return ''.join['{', self.text, ', ', str(self.avg_y), ', ', str(self.height), ', ', str(self.start_x), '}']

class KTPInformation(object):
    def __init__(self):
        self.nik = ""
        self.nama = ""
        self.tempat_lahir = ""
        self.tanggal_lahir = ""
        self.jenis_kelamin = ""
        self.golongan_darah = ""
        self.alamat = ""
        self.rt = ""
        self.rw = ""
        self.kelurahan_atau_desa = ""
        self.kecamatan = ""
        self.agama = ""
        self.status_perkawinan = ""
        self.pekerjaan = ""
        self.kewarganegaraan = ""
        berlaku_hingga = "SEMUR HIDUP"

class KTPOCR(object):
    def __init__(self, image):
        self.image = image
        self.result = KTPInformation()
        self.master_process()

    def word_to_number_converter(self, word):
        word_dict = {
            '|' : "1"
        }
        # res = word
        # for letter in word:
        #     if letter in word_dict:
        #         res = res.replace(letter, word_dict[letter])
        res = ""
        for letter in word:
            if letter in word_dict:
                res += word_dict[letter]
            else:
                res += letter
        return res


    def nik_extract(self, word):
        word_dict = {
            'b' : "6",
            'e' : "2",
        }
        # res = word
        # for letter in word:
        #     if letter in word_dict:
        #         res = res.replace(letter, word_dict[letter])
        res = ""
        for letter in word:
            if letter in word_dict:
                res += word_dict[letter]
            else:
                res += letter
        return res


    def error_dct(word):
        err = {'KARTU', 'KARTUS', 'KARTIS', 'KARTUN', 'KARTY', 'KARTI', 'KARTYN', 'KARTIN', 'KARTY', 'KART', 'RTU', 'ARTU', 'KAR', 'KA'}

    def extract(self, extracted_result):
        print(extracted_result)
        alamat = False
        KABUPATEN = ""
        KOTA = ""
        self.result.nik = extracted_result[0]
        for word in extracted_result:
            word = word.replace("*","").replace("MH", "").replace("{",'').replace("}", '').replace("(", '').replace(")",'').replace('KARTUJ',"").replace('KARTI', "").replace('KARTUT', "").replace('KARTUS', "").replace('KARIU', "").replace('KARTU',"").replace('KARTY',"").replace('KARTI',"").replace('KARTA', "").replace('KARTUN', '').replace('KART',"").replace('KAR',"").replace('EAT','')
            if "KABUPATEN" in word:
                KABUPATEN = word.replace("KABUPATEN ","")
            if "KOTA" in word:
                KOTA = word
            if "NIK" in word or "ΝΙΚ" in word:
                if word == "NIK:" or word == "NIK":
                    continue
                # word = word.split(':')
                items = [(''.join([n for n in item if n.isdigit()])) for item in word.split(':')]
                # items = []
                # for item in word.split(':'):
                #     items.append(''.join([n for n in item if n.isdigit()]))
                self.result.nik = self.nik_extract((''.join(items)).replace(" ", "").replace("NIK","").replace("ΝΙΚ",""))
                continue

            if "Nama" in word:
                word = word.split(':')
                self.result.nama = self.strip_accents(word[-1].replace('Nama','').replace("Nama-","").lstrip().rstrip())
                continue

            if "Tempat" in word or 'Lahir' in word:
                try:
                    word = word.split(':')
                    try:
                        self.result.tanggal_lahir = re.search("([0-9]{2}\-[0-9]{2}\-[0-9]{4})", word[-1])[0]
                    except:
                        self.result.tanggal_lahir = '-'
                    # word = re.search("([0-9]{2}\-[0-9]{2}\-[0-9]{4})", word[-1])[0]
                    word = re.sub("tempat|/|tgl|lahir|"+self.result.tanggal_lahir,'', word[-1], flags=re.IGNORECASE)
                    # self.result.tempat_lahir = word[-1].replace(self.result.tanggal_lahir, '').replace(",","").lstrip().rstrip()
                    self.result.tempat_lahir = word.replace(",","").lstrip().rstrip()
                    continue
                except:
                    raise

            if 'Darah' in word:
                self.result.jenis_kelamin = re.search("(LAKI- LAKI|LAKI-LAKI|LAKI - LAKI|LAKI|LELAKI|PEREMPUAN|MALE|FEMALE)", word)[0]
                word = word.split(':')
                try:
                    gol_dar = re.sub('status|perkawinan|kawin|gol. darah|nik|kewarganegaraan|nama|status perkawinan|berlaku hingga|alamat|agama|tempat/tgl lahir|jenis kelamin|gol darah|rt/rw|kel|desa|kecamatan|'+self.result.jenis_kelamin, '', word[-1], flags=re.IGNORECASE)
                    self.result.golongan_darah = re.search("(0|O|A|B|AB)",gol_dar)[0]
                    if self.result.golongan_darah == "0":
                        self.result.golongan_darah = "O"
                except:
                    self.result.golongan_darah = '-'
                self.result.jenis_kelamin = self.result.jenis_kelamin.strip().replace(" ","")

                print(word)
            if 'Alamat' in word:
                sub  = re.sub('status|perkawinan|kawin|gol. darah|nik|kewarganegaraan|nama|status perkawinan|berlaku hingga|alamat|agama|tempat/tgl lahir|jenis kelamin|gol darah|rt/rw|kel|desa|kecamatan', '', word, flags=re.IGNORECASE)
                self.result.alamat = self.word_to_number_converter(sub).replace("Alamat","").replace(":","").replace(":","").lstrip()
                alamat = True
                continue
            if alamat and (not "RT" in word or not "RW" in word) and (not "Kel" in word or not "Desa" in word) :
                self.result.alamat =  ''.join([self.result.alamat + " "+ self.word_to_number_converter(word).replace("Alamat","").replace(":","").lstrip()]) 
                # self.result.alamat = self.result.alamat + " "+ self.word_to_number_converter(word).replace("Alamat","").replace(":","").lstrip()
                alamat = False
            # if 'NO.' in word:
            #     self.result.alamat = self.result.alamat + ''+word
            if "Kecamatan" in word:
                if ":" in word:
                    self.result.kecamatan = word.split(':')[1].strip()
                else:
                    self.result.kecamatan = re.sub('status|perkawinan|kawin|gol. darah|nik|kewarganegaraan|nama|status perkawinan|berlaku hingga|alamat|agama|tempat/tgl lahir|jenis kelamin|gol darah|rt/rw|kel|desa|kecamatan', ' ', word, flags=re.IGNORECASE).lstrip()
                alamat = False  
            elif "Kecamata" in word:
                if ":" in word:
                    self.result.kecamatan = word.split(':')[1].strip()
                self.result.kecamatan = word.replace("Kecamata ", "").replace(' '+extracted_result[1],"")
            if "Desa" in word or "Kel" in word:
                wrd = word.split()
                desa = [wr for wr in wrd if not 'desa' in wr.lower() and not 'kel' in wr.lower() and not '/' in wr.lower()]
                # for wr in wrd:
                #     if not 'desa' in wr.lower() and not 'kel' in wr.lower() and not '/' in wr.lower():
                #         desa.append(wr)
                self.result.kelurahan_atau_desa = ' '.join(desa).replace('1 ', '')
                self.result.alamat = self.result.alamat.replace("  " + self.result.kelurahan_atau_desa,'').replace(" " + self.result.kelurahan_atau_desa,'')
                alamat = False
            if 'Kewarganegaraan' in word or 'negaraan' in word:
                replaces = ""
                try:
                    try:
                        sc = re.findall("([0-9]{2}\-[0-9]{2}\-[0-9]{4})", word)
                        replaces= ''.join(["|"+n for n in sc])
                    except:
                        replaces = ""
                    sub = re.sub('status|perkawinan|kawin|gol. darah|nik|kewarganegaraan|nama|status perkawinan|berlaku hingga|alamat|agama|tempat/tgl lahir|jenis kelamin|gol darah|rt/rw|kel|desa|kecamatan|ke varganegaraan|:| '+KABUPATEN+replaces, '', word, flags=re.IGNORECASE).replace(":","")
                    sub = re.sub('WNI[^"]*', "WNI", sub)     
                    self.result.kewarganegaraan = ''.join([n for n in sub if n.isalpha()]).replace("Berlaku", '').replace("Hingga", '').replace("i",'').replace("Barlaku",'')
                except:
                    self.result.golongan_darah = '-'  
                alamat = False
            if 'Pekerjaan' in word:
                wrod = word.split()
                for i in range(len(wrod)):
                   wrod[i] = re.sub('status|perkawinan|kawin|gol. darah|nik|kewarganegaraan|nama|status perkawinan|berlaku hingga|alamat|agama|tempat/tgl lahir|jenis kelamin|gol darah|rt/rw|kel|desa|kecamatan'+KABUPATEN, '', wrod[i], flags=re.IGNORECASE)
                pekerjaan = [wr for wr in wrod if not '-' in wr]
                # for wr in wrod:
                #     if not '-' in wr:
                #         pekerjaan.append(wr)
                self.result.pekerjaan = " ".join(pekerjaan).replace('ch','').replace('Pekerjaan', '').replace(':',"").replace("AU", '').replace("KARTUS","").replace(KABUPATEN,"").replace(KOTA,"").replace(self.result.kewarganegaraan,"").replace(word[1],"").replace("10 | 20", "").replace(self.result.kewarganegaraan,'').strip()
                if 'YAWAN' in self.result.pekerjaan:
                    self.result.pekerjaan = self.result.pekerjaan.replace('YAWAN','KARYAWAN').replace(' '+extracted_result[1],'')
                alamat = False
            if 'Agama' in word or 'Açoma' in word or 'Acoma' in word:
                sub = re.sub('status|perkawinan|kawin|gol. darah|nik|kewarganegaraan|nama|status perkawinan|berlaku hingga|alamat|agama|tempat/tgl lahir|jenis kelamin|gol darah|rt/rw|kel|desa|kecamatan|married|kartu'+KABUPATEN, '', word, flags=re.IGNORECASE).replace('Agama',"").replace(':',"").strip()
                # self.result.agama = re.search("(ISLAM|PROTESTAN|KATOLIK|HINDU|BUDDHA|KHONGHUCU)", word)[0].strip()
                if 'ISLAM' in word : self.result.agama = 'ISLAM'
                elif 'KRISTEN' in word: self.result.agama = 'KRISTEN'
                elif 'KATHOLIK' in word: self.result.agama = 'KATHOLIK'
                elif 'BUDHA' in word or 'BUDDHA' in word: self.result.agama = 'BUDDHA'
                elif 'HINDU' in word : self.result.agama = 'HINDU'
                elif 'KONGHUCHU' in word : self.result.agama = 'KONGHUCHU'
                else : self.result.agama = '-'
                alamat = False
            if 'Perkawinan' in word or 'awinan' in word:
                try:
                    self.result.status_perkawinan = re.search("(KAWIN|BELUM KAWIN|MARRIED|CERAI HIDUP|CERAI MATI)", word)[0].strip()
                    continue
                except:
                    raise
            if "RTRW" in word:
                word = word.replace("RTRW",'').replace(':',"")
                self.result.rt = word.split('/')[0].strip()
                self.result.rw = word.split('/')[1].strip()
                alamat = False
            elif "RT / RW" in word:
                try:
                    word = word.replace("RT / RW",'').replace(':',"").strip()
                    self.result.rt = word.split('/')[0].strip()
                    self.result.rw = word.split('/')[1].strip()
                except:
                    self.result.rt = "000"
                    self.result.rw = "000"
                alamat = False
            if "kelamin" in word:
                word = word.replace("Jenis kelamin", '').replace(':',"")
                self.result.jenis_kelamin = word


    def get_extended_annotations(self, response):

        extended_annotations = [ExtendedAnnotation(annotation) for annotation in response.text_annotations]
        # for annotation in response.text_annotations:
        #     extended_annotations.append(ExtendedAnnotation(annotation))

        # delete last item, as it is the whole text I guess.
        del extended_annotations[0]
        return extended_annotations

    def get_threshold_for_y_difference(self,annotations):
        annotations.sort(key=attrgetter('avg_y'))
        differences = [(abs(annotations[i].avg_y - annotations[i - 1].avg_y)) for i in range(0, len(annotations)) if i != 0]
        # for i in range(0, len(annotations)):
        #     if i == 0:
        #         continue
        #     differences.append(abs(annotations[i].avg_y - annotations[i - 1].avg_y))
        return np.std(differences)

    def group_annotations(self,annotations, threshold):
        annotations.sort(key=attrgetter('avg_y'))
        line_index = 0
        # text = [i[annotations[i]] for i in range(0, len(annotations)) if abs(annotations[i].avg_y - annotations[i - 1].avg_y) > threshold]
        text = [[]]
        for i in range(0, len(annotations)):
            if i == 0:
                text[line_index].append(annotations[i])
                continue
            y_difference = abs(annotations[i].avg_y - annotations[i - 1].avg_y)
            if y_difference > threshold:
                line_index += 1
                text.append([])
            text[line_index].append(annotations[i])
        return text

    def sort_and_combine_grouped_annotations(self,annotation_lists):
        grouped_list = []
        for annotation_group in annotation_lists:
            annotation_group.sort(key=attrgetter('start_x'))
            texts = re.sub(r'\s([-;:?.?](?:\s|$))', r'\1', ' '.join((o.text for o in annotation_group)))
            # texts = (o.text for o in annotation_group)
            # texts = ' '.join(texts)
            # texts = re.sub(r'\s([-;:?.!](?:\s|$))', r'\1', texts)
            grouped_list.append(texts)
        return grouped_list
    

    def detect_text(self, path):
        content = ''
        """Detects text in the file."""
        client = vision.ImageAnnotatorClient()
        if type(path) == str:
            with io.open(path, 'rb') as image_file:
                content = image_file.read()
        elif type(path) == bytes:
            content = path

        image = vision.Image(content=content)

        response = client.text_detection(image=image)
        # texts = response.text_annotations
        return response

    
    def master_process(self):
        responseGVission = self.detect_text(self.image)
        extendedAnnotaion =self.get_extended_annotations(responseGVission)
        threshold = self.get_threshold_for_y_difference(extendedAnnotaion)
        groupAnotation = self.group_annotations(extendedAnnotaion, threshold)
        sortedGroupAnnotation = self.sort_and_combine_grouped_annotations(groupAnotation)
        self.extract(sortedGroupAnnotation)

    def strip_accents(self, s):
        return ''.join(c for c in unicodedata.normalize('NFD', s)
                        if unicodedata.category(c) != 'Mn')
    
    def to_json(self):
        return json.dumps(self.result.__dict__, indent=4)

dt = datetime.now()
ts = datetime.timestamp(dt)
filename='img.jpg'
    
@app.route('/ocr/ktp', methods=['POST','GET'])
@token_required
@cross_origin()
def scan():
    filepath = ''
    if request.method == 'POST':
        if 'ktp' in request.files:
            try:
                file = request.files['ktp']
                filektp = file.read()
                filepath = 'file.pdf'
                f = open('file.pdf', 'wb')
                f.write(filektp)
                f.close()
            except OSError as err:
                print(err)
                return jsonify({"status": 500,
                                "data": {"timestamp": ts },
                                "message": "internal server error",
                                "result": str(err)}), 500
        elif 'ktp' in request.json:
            try:
                file = request.json['ktp']
                data_split = file.split(",")
                file_64 = data_split[1]
                bbytes = base64.b64decode(file_64, validate=True)
                if bbytes[0:4] != b'%PDF':
                    return jsonify({"status": 400, 
                                    "data": {"timestamp": ts }, 
                                    "message": "Missing the PDF file signature", 
                                    "success": "false" }), 400
                filepath = 'file.pdf'
                f = open('file.pdf', 'wb')
                f.write(bbytes)
                f.close()
            except OSError as err:
                print(err)
                return jsonify({"status": 500,
                                "data": {"timestamp": ts },
                                "message": "internal server error",
                                "result": str(err)}), 500
        try:
            pages = pdf2image.convert_from_path(filepath, poppler_path=r'./poppler-23.05.0/Library/bin')
            filename='img.jpg'
        except OSError as err:
            return jsonify({"status" : 400,
                            "data": {"timestamp": ts },
                            "message":"error while converting to image",
                            "success": "false"}), 400

        if len(pages) == 1:
            if os.path.exists(filepath):
                    os.remove(filepath)
            pages[0].save(filename, 'JPEG')
        else:
            if os.path.exists(filepath):
                    os.remove(filepath)
            return jsonify({"status": 400, 
                            "data": {"timestamp": ts }, 
                            "message": "pdf page more than 1", 
                            "success": "false" }), 400
        if filename == '':
            return jsonify({"status": 400, 
                            "data": {"timestamp": ts }, 
                            "message": "Bad Request, No Selected File", 
                            "success": "false" }), 400
        
        if file:
            try:
                with io.open(filename, 'rb') as image_file:
                    imgbites = image_file.read()
            except OSError as err:
                if os.path.exists(filename):
                    os.remove(filename)
                return jsonify({"status": 500,
                                "data": {"timestamp": ts },
                                "message": "internal server error",
                                "result": str(err)}), 500
            try:
                word = KTPOCR(imgbites)  
            except OSError as err:
                if os.path.exists(filename):
                    os.remove(filename)
                return jsonify({"status": 500,
                                "data": {"timestamp": ts },
                                "message": "internal server error",
                                "result": str(err)}), 500
            if word == "":
                return jsonify({"status": 404,
                                "data": {"timestamp": ts },
                                "message": "No Identity Card Detected",
                                "result": None}), 404
            jsonStr = word.to_json()
            if os.path.exists(filename):
                os.remove(filename)
            return jsonify(status = 200,message="OK",success="true", data=json.loads(jsonStr)), 200
        
        return jsonify({"status": 400, 
                        "data": {"timestamp": ts }, 
                        "message": "Bad Request", 
                        "success": "false" }), 400

@app.route('/')
@cross_origin()
def start():
    return jsonify({"status": 200, 
                    "data": {"timestamp": ts }, 
                    "message": "OK", 
                    "success": "success" }), 200

@app.route(str(SWAGGER_URL)+'/swagger.json')
@cross_origin()
def swagger():
	return send_file("./swagger.json")

if __name__ == '__main__':
    try:
        http_server = WSGIServer(("0.0.0.0", 6458), app)
        http_server.serve_forever()
    except SystemExit:
        pass
