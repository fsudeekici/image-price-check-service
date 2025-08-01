from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
from dotenv import load_dotenv
import os
import jwt
from datetime import datetime, timedelta, timezone
import psycopg2

load_dotenv()

app = Flask(__name__)

# CORS configuration - Update allowed origins for your deployment
CORS(app,
     support_credentials=True,
     origins=["https://your-frontend-domain.com"],  # Update this with your frontend domain
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
     )

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')


# Connect to the main database
def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))


# Decode the token and return user info
def decode_token(token):
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# Login endpoint
@app.route('/login', methods=['POST', 'OPTIONS'])
@cross_origin(supports_credentials=True)
def login():
    if request.method == 'OPTIONS':
        return '', 200

    data = request.json
    user_name = data.get('user_name')
    password = data.get('password')

    # Check if email and password are given
    if not user_name or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, user_name, password FROM neocortex_schema_v1.neolabel_users WHERE user_name = %s",
                (user_name,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    # If user not found
    if user is None:
        return jsonify({'error': 'User not found'}), 404

    user_id, user_name, stored_password = user

    # Check password
    if password != stored_password:
        return jsonify({'error': 'Wrong password'}), 401

    # Create token valid for 10 hours
    token = jwt.encode({
        'user_id': user_id,
        'exp': datetime.now(timezone.utc) + timedelta(hours=10)
    }, app.config['SECRET_KEY'], algorithm='HS256')

    return jsonify({'token': token})


# Database settings - Configure these environment variables
DB_CONFIGS = {

}


# Get product data from the database
def get_products_from_db(db_url, schema_name):
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    query = f'SELECT classes_id, classes_name, sap_code FROM {schema_name}.products_master ORDER BY classes_id'
    cur.execute(query)
    products = cur.fetchall()
    cur.close()
    conn.close()
    return products


# Get products by project name
@app.route('/getProducts', methods=['POST', 'OPTIONS'])
@cross_origin(supports_credentials=True)
def get_products():
    if request.method == 'OPTIONS':
        return '', 200

    data = request.json
    project_name = data.get('project_name')

    # Check if project name is valid
    if not project_name or project_name not in DB_CONFIGS:
        return jsonify({"error": "Invalid or missing project name"}), 400

    config = DB_CONFIGS[project_name]
    db_url = config['url']
    schema_name = config['schema']

    try:
        products = get_products_from_db(db_url, schema_name)
    except Exception as e:
        return jsonify({"error": f"Database error: {str(e)}"}), 500

    product_list = [
        {"class id": p[0], "class name": p[1], "sap code": p[2]} for p in products
    ]

    return jsonify(product_list)


# Save image process info
@app.route('/imageCheckResult', methods=['POST', 'OPTIONS'])
@cross_origin(supports_credentials=True)
def save_image_check_process():
    if request.method == 'OPTIONS':
        return '', 200

    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({'error': 'Authorization required'}), 401

    try:
        token = auth_header.split(" ")[1]
    except IndexError:
        return jsonify({'error': 'Invalid token format'}), 401

    payload = decode_token(token)
    if not payload:
        return jsonify({'error': 'Invalid or expired token'}), 401

    user_id = payload.get('user_id')
    data = request.get_json()

    project_name = data.get('project_name')
    if not project_name:
        return jsonify({'error': 'project_name is required'}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT user_name FROM neocortex_schema_v1.neolabel_users WHERE id = %s", (user_id,))
        user_result = cur.fetchone()
        if not user_result:
            return jsonify({'error': 'User not found'}), 404
        username = user_result[0]

        file_name = data.get('file_name')
        notdetected = data.get('notdetected_products', [])
        misdetected = data.get('misdetected_products', [])
        duplicate = data.get('duplicate_products', [])
        new_prods = data.get('new_products', [])
        incorrect_image_type = data.get('incorrect_image_type')
        note = data.get('note')
        perfect_image = data.get('perfect_image', False)

        # Perfect image kontrolü: file_name dolu, diğer alanlar boş ise perfect_image = True
        if (file_name and
                not notdetected and
                not misdetected and
                not duplicate and
                not new_prods and
                not incorrect_image_type and
                not note):
            perfect_image = True

        cur.execute("""
            INSERT INTO neocortex_schema_v1.neolabel_image_check_result (
                user_name, date_time, project_name, file_name,
                notdetected_products, misdetected_products,
                duplicate_products, incorrect_image_type,
                new_products, note, perfect_image
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            username,
            datetime.now(timezone.utc),
            project_name,
            file_name,
            notdetected,
            misdetected,
            duplicate,
            incorrect_image_type,
            new_prods,
            note,
            perfect_image
        ))
        cur.execute("""
                    SELECT setval(
          'neocortex_schema_v1.neolabel_image_check_result_id_seq',
          (SELECT MAX(id) + 1 FROM neocortex_schema_v1.neolabel_image_check_result),
          false
        );
        """)

        conn.commit()
        cur.close()
        conn.close()

        return jsonify({'message': 'Saved successfully'}), 201

    except Exception as e:
        return jsonify({'error': f'Database error: {str(e)}'}), 500


# Get info texts
@app.route('/getInfoTexts', methods=['GET', 'OPTIONS'])
@cross_origin(supports_credentials=True)
def get_info_texts():
    if request.method == 'OPTIONS':
        return '', 200

    info_texts = [
        {
            "id": "file_name",
            "label": "Fotoğraf İsmi",
            "help": "Kontrol edilen fotoğrafın dosya adını giriniz. (örn: 171629795-7403-193-C-1.jpg)"
        },
        {
            "id": "notdetected_products",
            "label": "Tespit Edilemeyen Ürünler",
            "help": "Fotoğrafta bulunmasına rağmen sistem tarafından tespit edilemeyen ürünlerin listesini giriniz."
        },
        {
            "id": "misdetected_products",
            "label": "Yanlış Tespit Edilen Ürünler",
            "help": "Sistem tarafından yanlış tanımlanan ürünleri giriniz."
        },
        {
            "id": "duplicate_products",
            "label": "Duplike Ürünler",
            "help": "Fotoğrafta bir üründe birden fazla etiket varsa, bu ürünleri giriniz."
        },
        {
            "id": "new_products",
            "label": "Yeni Ürünler",
            "help": "Katalogda bulunmayan ancak fotoğrafta görünen yeni ürünlerin listesini giriniz."
        },
        {
            "id": "incorrect_image_type",
            "label": "Hatalı Görüntü Tipi",
            "help": "Fotoğrafın ışık durumu, açısı vs. uygun değilse belirtiniz."
        },
        {
            "id": "note",
            "label": "Not",
            "help": "Ek açıklamalar, özel durumlar veya diğer gözlemlerinizi buraya yazınız."
        }
    ]

    return jsonify(info_texts), 200


# Get user daily check count
@app.route('/getUserDailyCheckCount', methods=['GET', 'OPTIONS'])
@cross_origin(supports_credentials=True)
def get_user_daily_check_count():
    if request.method == 'OPTIONS':
        return '', 200

    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({'error': 'Authorization required'}), 401

    try:
        token = auth_header.split(" ")[1]
    except IndexError:
        return jsonify({'error': 'Invalid token format'}), 401

    payload = decode_token(token)
    if not payload:
        return jsonify({'error': 'Invalid or expired token'}), 401

    user_id = payload.get('user_id')

    project_name = request.args.get('project_name')
    if not project_name:
        return jsonify({'error': 'project_name query parameter is required'}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT user_name FROM neocortex_schema_v1.neolabel_users WHERE id = %s", (user_id,))
        user_result = cur.fetchone()
        if not user_result:
            return jsonify({'error': 'User not found'}), 404
        username = user_result[0]

        today = datetime.now(timezone.utc).date()

        cur.execute("""
            SELECT COUNT(*) FROM neocortex_schema_v1.neolabel_image_check_result
            WHERE user_name = %s
              AND project_name = %s
              AND DATE(date_time AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Istanbul') = %s
        """, (username, project_name, today))

        count_result = cur.fetchone()
        count = count_result[0] if count_result else 0

        cur.close()
        conn.close()

        return jsonify({
            "user_name": username,
            "project_name": project_name,
            "date": str(today),
            "checked_files_count": count
        })

    except Exception as e:
        return jsonify({'error': f'Database error: {str(e)}'}), 500


# Save price tag check result - PTC
@app.route('/savePriceTagCheckResult', methods=['POST', 'OPTIONS'])
@cross_origin(supports_credentials=True)
def save_price_tag_check_result():
    if request.method == 'OPTIONS':
        return '', 200

    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({'error': 'Authorization required'}), 401
    try:
        token = auth_header.split(" ")[1]
    except IndexError:
        return jsonify({'error': 'Invalid token format'}), 401
    payload = decode_token(token)
    if not payload:
        return jsonify({'error': 'Invalid or expired token'}), 401

    user_id = payload.get('user_id')
    if not user_id:
        return jsonify({'error': 'User ID missing in token'}), 401

    data = request.get_json()
    project_name = data.get('project_name')
    if not project_name or project_name not in DB_CONFIGS:
        return jsonify({'error': 'Invalid or missing project_name'}), 400

    try:
        main_conn = get_db_connection()
        main_cur = main_conn.cursor()
        main_cur.execute("SELECT user_name FROM neocortex_schema_v1.neolabel_users WHERE id = %s", (user_id,))
        user_result = main_cur.fetchone()
        if not user_result:
            main_cur.close()
            main_conn.close()
            return jsonify({'error': 'User not found'}), 404
        user_name = user_result[0]
        main_cur.close()
        main_conn.close()

        # for perfect_pta_image
        try:
            total = int(data.get('total_label_count'))
        except:
            total = 0
        try:
            valid = int(data.get('valid_digit_label_count'))
        except:
            valid = 0
        try:
            correct_price = int(data.get('correct_price_read_count'))
        except:
            correct_price = 0
        try:
            correct_product = int(data.get('correct_product_detected_count'))
        except:
            correct_product = 0
        incorrect_type = data.get('incorrect_image_type')

        perfect_pta = False
        if not incorrect_type.strip() and total:
            if total == valid == correct_price == correct_product:
                perfect_pta = True

        main_conn = get_db_connection()
        main_cur = main_conn.cursor()
        main_cur.execute("""
            INSERT INTO neocortex_schema_v1.neolabel_price_tag_check_result (
                user_name, project_name, file_name,
                total_label_count, valid_digit_label_count,
                correct_price_read_count, correct_product_detected_count,
                incorrect_image_type, date_time, note, perfect_pta_image
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_name,
            project_name,
            data.get('file_name', ''),
            0 if data.get('total_label_count') == '' else int(data.get('total_label_count')),
            0 if data.get('valid_digit_label_count') == '' else int(data.get('valid_digit_label_count')),
            0 if data.get('correct_price_read_count') == '' else int(data.get('correct_price_read_count')),
            0 if data.get('correct_product_detected_count') == '' else int(data.get('correct_product_detected_count')),
            data.get('incorrect_image_type', ''),
            datetime.now(timezone.utc),
            data.get('note'),
            perfect_pta
        ))

        main_conn.commit()
        main_cur.close()
        main_conn.close()

        return jsonify({'message': 'Saved successfully'}), 201

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Database error: {str(e)}'}), 500


# Get price tag info texts - PTC
@app.route('/getPriceTagInfoTexts', methods=['GET', 'OPTIONS'])
@cross_origin(supports_credentials=True)
def get_price_tag_info_texts():
    if request.method == 'OPTIONS':
        return '', 200

    info_texts = [
        {
            "id": "file_name",
            "label": "Fotoğraf İsmi",
            "help": "Kontrol edilen fiyat etiketi fotoğrafının dosya adını giriniz. (örn: 171629795-7403-193-C-1.jpg)"
        },
        {
            "id": "incorrect_image_type",
            "label": "Hatalı Görüntü Tipi",
            "help": "Fotoğrafın kalitesi, ışık durumu, açısı vs. uygun değilse belirtiniz."
        },
        {
            "id": "total_label_count",
            "label": "Toplam Etiket Sayısı",
            "help": "Fotoğrafta bulunan toplam fiyat etiketi sayısını giriniz."
        },
        {
            "id": "valid_digit_label_count",
            "label": "Kurallara Uygun Etiket Sayısı",
            "help": "Fiyat etiket standartlarına uyan etiket sayısını giriniz."
        },
        {
            "id": "correct_price_read_count",
            "label": "Doğru Fiyat Okuma Sayısı",
            "help": "Sistem tarafından doğru olarak okunan fiyat sayısını giriniz."
        },
        {
            "id": "correct_product_detected_count",
            "label": "Doğru Ürün Tespit Sayısı",
            "help": "Sistem tarafından doğru olarak tespit edilen ürün sayısını giriniz."
        },
        {
            "id": "note",
            "label": "Not",
            "help": "Ek açıklamalar, özel durumlar veya diğer gözlemlerinizi buraya yazınız."
        }
    ]

    return jsonify(info_texts), 200


# Get user daily price tag check count - PTC
@app.route('/getPtcUserDailyPriceTagCheckCount', methods=['POST', 'OPTIONS'])
@cross_origin(supports_credentials=True)
def get_user_daily_price_tag_check_count():
    if request.method == 'OPTIONS':
        return '', 200

    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({'error': 'Authorization required'}), 401

    try:
        token = auth_header.split(" ")[1]
    except IndexError:
        return jsonify({'error': 'Invalid token format'}), 401

    payload = decode_token(token)
    if not payload:
        return jsonify({'error': 'Invalid or expired token'}), 401

    user_id = payload.get('user_id')

    data = request.get_json()
    if not data:
        return jsonify({'error': 'JSON body is required'}), 400

    project_name = data.get('project_name')
    if not project_name:
        return jsonify({'error': 'project_name is required in JSON body'}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT user_name FROM neocortex_schema_v1.neolabel_users WHERE id = %s", (user_id,))
        user_result = cur.fetchone()
        if not user_result:
            return jsonify({'error': 'User not found'}), 404
        username = user_result[0]

        today = datetime.now(timezone.utc).date()

        cur.execute("""
            SELECT COUNT(*) FROM neocortex_schema_v1.neolabel_price_tag_check_result
            WHERE user_name = %s
              AND project_name = %s
              AND DATE(date_time AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Istanbul') = %s
        """, (username, project_name, today))

        count_result = cur.fetchone()
        count = count_result[0] if count_result else 0

        cur.close()
        conn.close()

        return jsonify({
            "user_name": username,
            "project_name": project_name,
            "date": str(today),
            "checked_files_count": count
        })

    except Exception as e:
        return jsonify({'error': f'Database error: {str(e)}'}), 500


if __name__ == '__main__':
    # Use environment variables for production deployment
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))

    app.run(debug=debug_mode, host=host, port=port)