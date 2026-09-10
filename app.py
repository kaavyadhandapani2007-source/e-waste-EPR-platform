import os
import uuid
import hashlib
from datetime import datetime, timezone
from functools import wraps

import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import jwt


# ============================================================
# E-WASTE EPR PLATFORM
# Flask + PostgreSQL + psycopg2
# NO SQLAlchemy
# ============================================================

app = Flask(__name__, static_folder="frontend", static_url_path="/")
CORS(app)

app.config["SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "CHANGE_THIS_SECRET")
DATABASE_URL = os.getenv("DATABASE_URL")

DEMO_BRAND = "ECOGEN Electronics"
DEMO_EPR_OBLIGATION = 10000.0

CUSTOMER_POINTS_PER_KG = 5
COLLECTOR_POINTS_PER_KG = 10

WEIGHT_TOLERANCE = 0.20


# ============================================================
# DATABASE
# ============================================================

def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is not configured.")

    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor,
        sslmode="require"
    )


def db_execute(query, params=None, fetchone=False, fetchall=False,
               commit=False):
    conn = get_db()

    try:
        cur = conn.cursor()
        cur.execute(query, params or ())

        result = None

        if fetchone:
            result = cur.fetchone()
        elif fetchall:
            result = cur.fetchall()

        if commit:
            conn.commit()

        cur.close()
        return result

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def generate_id(prefix):
    return f"{prefix}-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def utc_now():
    return datetime.now(timezone.utc)


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(30),
    password_hash TEXT NOT NULL,
    role VARCHAR(30) NOT NULL,
    profile_photo TEXT,
    language VARCHAR(20) DEFAULT 'en-IN',
    address TEXT,
    city VARCHAR(100),
    state VARCHAR(100),
    pincode VARCHAR(20),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    is_verified BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_login TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    customer_id VARCHAR(50) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS collectors (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    collector_id VARCHAR(50) UNIQUE NOT NULL,
    collection_area VARCHAR(255),
    government_id VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS aggregators (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    aggregator_id VARCHAR(50) UNIQUE NOT NULL,
    organization_name VARCHAR(255),
    operating_area VARCHAR(255),
    gstin VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS recyclers (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    recycler_id VARCHAR(50) UNIQUE NOT NULL,
    organization_name VARCHAR(255),
    authorization_number VARCHAR(150),
    processing_capacity NUMERIC(12,2),
    gstin VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS brands (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    brand_id VARCHAR(50) UNIQUE NOT NULL,
    brand_name VARCHAR(255) NOT NULL,
    organization_name VARCHAR(255),
    authorized_person VARCHAR(255),
    gstin VARCHAR(100),
    cpcb_registration_number VARCHAR(150),
    epr_obligation NUMERIC(14,2) DEFAULT 10000,
    logo TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS handovers (
    id SERIAL PRIMARY KEY,
    handover_id VARCHAR(50) UNIQUE NOT NULL,
    customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    brand_id INTEGER REFERENCES brands(id) ON DELETE SET NULL,
    product_category VARCHAR(150),
    product_name VARCHAR(255),
    brand_name VARCHAR(255),
    model VARCHAR(255),
    serial_number VARCHAR(255),
    imei VARCHAR(255),
    quantity NUMERIC(12,2),
    estimated_weight NUMERIC(12,2),
    pickup_location TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    phone VARCHAR(30),
    notes TEXT,
    product_photo TEXT,
    status VARCHAR(50) DEFAULT 'HANDOVER_REQUESTED',
    assigned_collector_id INTEGER REFERENCES collectors(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS collections (
    id SERIAL PRIMARY KEY,
    collection_id VARCHAR(50) UNIQUE NOT NULL,
    handover_id INTEGER REFERENCES handovers(id) ON DELETE SET NULL,
    customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    collector_id INTEGER REFERENCES collectors(id) ON DELETE SET NULL,
    aggregator_id INTEGER REFERENCES aggregators(id) ON DELETE SET NULL,
    recycler_id INTEGER REFERENCES recyclers(id) ON DELETE SET NULL,
    brand_id INTEGER REFERENCES brands(id) ON DELETE SET NULL,
    item_category VARCHAR(150),
    product_name VARCHAR(255),
    brand_name VARCHAR(255),
    quantity NUMERIC(12,2),
    declared_weight NUMERIC(12,2),
    collector_weight NUMERIC(12,2),
    aggregator_weight NUMERIC(12,2),
    recycler_weight NUMERIC(12,2),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    gps_accuracy DOUBLE PRECISION,
    image_hash VARCHAR(128),
    collection_photo TEXT,
    receiving_photo TEXT,
    status VARCHAR(50) DEFAULT 'COLLECTED',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS verification_records (
    id SERIAL PRIMARY KEY,
    collection_id INTEGER REFERENCES collections(id) ON DELETE CASCADE,
    verifier_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    verification_type VARCHAR(50) NOT NULL,
    weight NUMERIC(12,2),
    status VARCHAR(50),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS collector_locations (
    id SERIAL PRIMARY KEY,
    collector_id INTEGER REFERENCES collectors(id) ON DELETE CASCADE,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    accuracy DOUBLE PRECISION,
    status VARCHAR(50),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS epr_records (
    id SERIAL PRIMARY KEY,
    epr_id VARCHAR(50) UNIQUE NOT NULL,
    collection_id INTEGER UNIQUE REFERENCES collections(id) ON DELETE CASCADE,
    brand_id INTEGER REFERENCES brands(id) ON DELETE SET NULL,
    recycler_id INTEGER REFERENCES recyclers(id) ON DELETE SET NULL,
    verified_weight NUMERIC(12,2) NOT NULL,
    material VARCHAR(150),
    status VARCHAR(50) DEFAULT 'EPR_VERIFIED',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS epr_documents (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(50) UNIQUE NOT NULL,
    brand_id INTEGER REFERENCES brands(id) ON DELETE CASCADE,
    financial_year VARCHAR(20),
    epr_obligation NUMERIC(14,2),
    verified_weight NUMERIC(14,2),
    compliance_percentage NUMERIC(8,3),
    file_path TEXT,
    status VARCHAR(50) DEFAULT 'GENERATED',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reward_transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    collection_id INTEGER REFERENCES collections(id) ON DELETE SET NULL,
    role VARCHAR(30),
    points NUMERIC(12,2) NOT NULL,
    transaction_type VARCHAR(50),
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    role VARCHAR(30),
    action VARCHAR(100),
    entity VARCHAR(100),
    entity_id VARCHAR(100),
    previous_status VARCHAR(100),
    new_status VARCHAR(100),
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS anomaly_flags (
    id SERIAL PRIMARY KEY,
    collection_id INTEGER REFERENCES collections(id) ON DELETE CASCADE,
    anomaly_type VARCHAR(100),
    severity VARCHAR(30),
    description TEXT,
    status VARCHAR(50) DEFAULT 'OPEN',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255),
    message TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);
CREATE INDEX IF NOT EXISTS idx_handover_status ON handovers(status);
CREATE INDEX IF NOT EXISTS idx_collection_status ON collections(status);
CREATE INDEX IF NOT EXISTS idx_collection_brand ON collections(brand_id);
CREATE INDEX IF NOT EXISTS idx_collection_collector ON collections(collector_id);
CREATE INDEX IF NOT EXISTS idx_locations_collector ON collector_locations(collector_id);
CREATE INDEX IF NOT EXISTS idx_locations_timestamp ON collector_locations(timestamp);
CREATE INDEX IF NOT EXISTS idx_collection_image_hash ON collections(image_hash);
CREATE INDEX IF NOT EXISTS idx_collection_serial ON collections(serial_number);
CREATE INDEX IF NOT EXISTS idx_epr_brand ON epr_records(brand_id);
"""


@app.route("/api/setup-db", methods=["POST"])
def setup_db():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(SCHEMA)
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "success": True,
            "message": "PostgreSQL database initialized successfully."
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================
# AUTH HELPERS
# ============================================================

def create_token(user):
    payload = {
        "user_id": user["id"],
        "role": user["role"],
        "exp": datetime.now(timezone.utc).timestamp() + (24 * 60 * 60)
    }

    return jwt.encode(
        payload,
        app.config["SECRET_KEY"],
        algorithm="HS256"
    )


def get_token():
    header = request.headers.get("Authorization", "")

    if not header.startswith("Bearer "):
        return None

    return header.split(" ", 1)[1]


def current_user():
    token = get_token()

    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
            app.config["SECRET_KEY"],
            algorithms=["HS256"]
        )

        return db_execute(
            """
            SELECT *
            FROM users
            WHERE id = %s
              AND is_active = TRUE
            """,
            (payload["user_id"],),
            fetchone=True
        )

    except Exception:
        return None


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()

        if not user:
            return jsonify({
                "success": False,
                "error": "Authentication required."
            }), 401

        return fn(user, *args, **kwargs)

    return wrapper


def roles_required(*allowed_roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(user, *args, **kwargs):

            if user["role"] not in allowed_roles:
                return jsonify({
                    "success": False,
                    "error": "Unauthorized role."
                }), 403

            return fn(user, *args, **kwargs)

        return wrapper

    return decorator


# ============================================================
# AUDIT
# ============================================================

def audit(user_id, role, action, entity, entity_id,
          previous_status=None, new_status=None, metadata=None):

    db_execute(
        """
        INSERT INTO audit_logs
        (
            user_id,
            role,
            action,
            entity,
            entity_id,
            previous_status,
            new_status,
            metadata
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            user_id,
            role,
            action,
            entity,
            str(entity_id),
            previous_status,
            new_status,
            psycopg2.extras.Json(metadata or {})
        ),
        commit=True
    )


def notify(user_id, title, message):

    db_execute(
        """
        INSERT INTO notifications
        (user_id, title, message)
        VALUES (%s,%s,%s)
        """,
        (user_id, title, message),
        commit=True
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():
    try:
        db_execute("SELECT 1", fetchone=True)

        return jsonify({
            "status": "healthy",
            "database": "connected",
            "service": "E-Waste EPR Platform"
        })

    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "database": "error",
            "error": str(e)
        }), 500


@app.route("/api/status")
def status():
    return jsonify({
        "status": "online",
        "platform": "E-Waste EPR Platform",
        "database": "PostgreSQL",
        "orm": "None - psycopg2"
    })


# ============================================================
# REGISTER
# ============================================================

@app.route("/api/auth/register", methods=["POST"])
def register():

    data = request.get_json() or {}

    required = [
        "full_name",
        "email",
        "password",
        "role"
    ]

    for field in required:
        if not data.get(field):
            return jsonify({
                "success": False,
                "error": f"{field} is required."
            }), 400

    role = data["role"].upper()

    allowed_roles = [
        "USER",
        "COLLECTOR",
        "AGGREGATOR",
        "RECYCLER",
        "BRAND_PRO"
    ]

    if role not in allowed_roles:
        return jsonify({
            "success": False,
            "error": "Invalid role."
        }), 400

    email = data["email"].strip().lower()

    existing = db_execute(
        "SELECT id FROM users WHERE email = %s",
        (email,),
        fetchone=True
    )

    if existing:
        return jsonify({
            "success": False,
            "error": "Email already registered."
        }), 409

    password_hash = generate_password_hash(data["password"])

    conn = get_db()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO users
            (
                full_name,
                email,
                phone,
                password_hash,
                role,
                language,
                address,
                city,
                state,
                pincode,
                latitude,
                longitude,
                is_verified
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                data["full_name"],
                email,
                data.get("phone"),
                password_hash,
                role,
                data.get("language", "en-IN"),
                data.get("address"),
                data.get("city"),
                data.get("state"),
                data.get("pincode"),
                data.get("latitude"),
                data.get("longitude"),
                False
            )
        )

        user_id = cur.fetchone()["id"]

        if role == "USER":
            role_id = generate_id("USR")

            cur.execute(
                """
                INSERT INTO customers
                (user_id, customer_id)
                VALUES (%s,%s)
                """,
                (user_id, role_id)
            )

        elif role == "COLLECTOR":
            role_id = generate_id("COL")

            cur.execute(
                """
                INSERT INTO collectors
                (user_id, collector_id, collection_area, government_id)
                VALUES (%s,%s,%s,%s)
                """,
                (
                    user_id,
                    role_id,
                    data.get("collection_area"),
                    data.get("government_id")
                )
            )

        elif role == "AGGREGATOR":
            role_id = generate_id("AGG")

            cur.execute(
                """
                INSERT INTO aggregators
                (
                    user_id,
                    aggregator_id,
                    organization_name,
                    operating_area,
                    gstin
                )
                VALUES (%s,%s,%s,%s,%s)
                """,
                (
                    user_id,
                    role_id,
                    data.get("organization_name"),
                    data.get("operating_area"),
                    data.get("gstin")
                )
            )

        elif role == "RECYCLER":
            role_id = generate_id("REC")

            cur.execute(
                """
                INSERT INTO recyclers
                (
                    user_id,
                    recycler_id,
                    organization_name,
                    authorization_number,
                    processing_capacity,
                    gstin
                )
                VALUES (%s,%s,%s,%s,%s,%s)
                """,
                (
                    user_id,
                    role_id,
                    data.get("organization_name"),
                    data.get("authorization_number"),
                    data.get("processing_capacity"),
                    data.get("gstin")
                )
            )

        elif role == "BRAND_PRO":
            role_id = generate_id("BRAND")

            cur.execute(
                """
                INSERT INTO brands
                (
                    user_id,
                    brand_id,
                    brand_name,
                    organization_name,
                    authorized_person,
                    gstin,
                    cpcb_registration_number,
                    epr_obligation
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    user_id,
                    role_id,
                    data.get("brand_name", data.get("organization_name")),
                    data.get("organization_name"),
                    data.get("authorized_person"),
                    data.get("gstin"),
                    data.get("cpcb_registration_number"),
                    data.get("epr_obligation", DEMO_EPR_OBLIGATION)
                )
            )

        conn.commit()
        cur.close()

        return jsonify({
            "success": True,
            "message": "Registration successful.",
            "user_id": user_id,
            "role_id": role_id,
            "role": role
        }), 201

    except Exception as e:
        conn.rollback()

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    finally:
        conn.close()


# ============================================================
# LOGIN
# ============================================================

@app.route("/api/auth/login", methods=["POST"])
def login():

    data = request.get_json() or {}

    identifier = (
        data.get("email")
        or data.get("phone")
        or ""
    ).strip()

    password = data.get("password", "")
    requested_role = data.get("role")

    if not identifier or not password:
        return jsonify({
            "success": False,
            "error": "Email/phone and password are required."
        }), 400

    user = db_execute(
        """
        SELECT *
        FROM users
        WHERE LOWER(email) = LOWER(%s)
           OR phone = %s
        """,
        (identifier, identifier),
        fetchone=True
    )

    if not user or not check_password_hash(
        user["password_hash"],
        password
    ):
        return jsonify({
            "success": False,
            "error": "Invalid login credentials."
        }), 401

    if requested_role:
        if user["role"] != requested_role.upper():
            return jsonify({
                "success": False,
                "error": "This account does not belong to the selected role."
            }), 403

    db_execute(
        """
        UPDATE users
        SET last_login = NOW(),
            updated_at = NOW()
        WHERE id = %s
        """,
        (user["id"],),
        commit=True
    )

    token = create_token(user)

    return jsonify({
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "name": user["full_name"],
            "email": user["email"],
            "phone": user["phone"],
            "role": user["role"],
            "language": user["language"]
        }
    })


# ============================================================
# CURRENT USER
# ============================================================

@app.route("/api/auth/me")
@login_required
def me(user):

    return jsonify({
        "success": True,
        "user": dict(user)
    })


# ============================================================
# PROFILE
# ============================================================

@app.route("/api/auth/profile", methods=["PUT"])
@login_required
def update_profile(user):

    data = request.get_json() or {}

    allowed = [
        "full_name",
        "phone",
        "language",
        "address",
        "city",
        "state",
        "pincode",
        "latitude",
        "longitude",
        "profile_photo"
    ]

    updates = []
    values = []

    for field in allowed:
        if field in data:
            updates.append(f"{field} = %s")
            values.append(data[field])

    if not updates:
        return jsonify({
            "success": False,
            "error": "No profile fields supplied."
        }), 400

    updates.append("updated_at = NOW()")
    values.append(user["id"])

    db_execute(
        f"""
        UPDATE users
        SET {", ".join(updates)}
        WHERE id = %s
        """,
        tuple(values),
        commit=True
    )

    return jsonify({
        "success": True,
        "message": "Profile updated."
    })


# ============================================================
# CHANGE PASSWORD
# ============================================================

@app.route("/api/auth/change-password", methods=["PUT"])
@login_required
def change_password(user):

    data = request.get_json() or {}

    old_password = data.get("old_password")
    new_password = data.get("new_password")

    if not old_password or not new_password:
        return jsonify({
            "success": False,
            "error": "Both passwords are required."
        }), 400

    if not check_password_hash(
        user["password_hash"],
        old_password
    ):
        return jsonify({
            "success": False,
            "error": "Current password is incorrect."
        }), 400

    db_execute(
        """
        UPDATE users
        SET password_hash = %s,
            updated_at = NOW()
        WHERE id = %s
        """,
        (
            generate_password_hash(new_password),
            user["id"]
        ),
        commit=True
    )

    return jsonify({
        "success": True,
        "message": "Password changed successfully."
    })


# ============================================================
# CUSTOMER HANDOVER
# ============================================================

@app.route("/api/customer/handover", methods=["POST"])
@login_required
@roles_required("USER")
def create_handover(user):

    data = request.get_json() or {}

    customer = db_execute(
        """
        SELECT *
        FROM customers
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    if not customer:
        return jsonify({
            "success": False,
            "error": "Customer profile not found."
        }), 404

    handover_id = generate_id("HO")

    brand_id = None
    brand_name = data.get("brand")

    if brand_name:
        brand = db_execute(
            """
            SELECT id
            FROM brands
            WHERE LOWER(brand_name) = LOWER(%s)
            """,
            (brand_name,),
            fetchone=True
        )

        if brand:
            brand_id = brand["id"]

    db_execute(
        """
        INSERT INTO handovers
        (
            handover_id,
            customer_id,
            brand_id,
            product_category,
            product_name,
            brand_name,
            model,
            serial_number,
            imei,
            quantity,
            estimated_weight,
            pickup_location,
            latitude,
            longitude,
            phone,
            notes,
            product_photo
        )
        VALUES
        (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            handover_id,
            customer["id"],
            brand_id,
            data.get("product_category"),
            data.get("product_name"),
            brand_name,
            data.get("model"),
            data.get("serial_number"),
            data.get("imei"),
            data.get("quantity", 1),
            data.get("estimated_weight", 0),
            data.get("pickup_location"),
            data.get("latitude"),
            data.get("longitude"),
            data.get("phone", user["phone"]),
            data.get("notes"),
            data.get("product_photo")
        ),
        commit=True
    )

    audit(
        user["id"],
        user["role"],
        "HANDOVER_CREATED",
        "handover",
        handover_id,
        new_status="HANDOVER_REQUESTED"
    )

    return jsonify({
        "success": True,
        "handover_id": handover_id,
        "status": "HANDOVER_REQUESTED"
    }), 201


@app.route("/api/customer/handovers")
@login_required
@roles_required("USER")
def customer_handovers(user):

    rows = db_execute(
        """
        SELECT h.*
        FROM handovers h
        JOIN customers c
          ON h.customer_id = c.id
        WHERE c.user_id = %s
        ORDER BY h.created_at DESC
        """,
        (user["id"],),
        fetchall=True
    )

    return jsonify({
        "success": True,
        "handovers": rows
    })


# ============================================================
# COLLECTOR PICKUPS
# ============================================================

@app.route("/api/collector/pickups")
@login_required
@roles_required("COLLECTOR")
def collector_pickups(user):

    collector = db_execute(
        """
        SELECT *
        FROM collectors
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    rows = db_execute(
        """
        SELECT
            h.*,
            c.collector_id
        FROM handovers h
        LEFT JOIN collectors c
          ON h.assigned_collector_id = c.id
        WHERE
            h.status = 'HANDOVER_REQUESTED'
            OR h.assigned_collector_id = %s
        ORDER BY h.created_at DESC
        """,
        (collector["id"],),
        fetchall=True
    )

    return jsonify({
        "success": True,
        "pickups": rows
    })


@app.route("/api/collector/pickups/<handover_id>/accept", methods=["POST"])
@login_required
@roles_required("COLLECTOR")
def accept_pickup(user, handover_id):

    collector = db_execute(
        """
        SELECT *
        FROM collectors
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    handover = db_execute(
        """
        SELECT *
        FROM handovers
        WHERE handover_id = %s
        """,
        (handover_id,),
        fetchone=True
    )

    if not handover:
        return jsonify({
            "success": False,
            "error": "Handover not found."
        }), 404

    db_execute(
        """
        UPDATE handovers
        SET assigned_collector_id = %s,
            status = 'COLLECTOR_ASSIGNED',
            updated_at = NOW()
        WHERE id = %s
        """,
        (collector["id"], handover["id"]),
        commit=True
    )

    audit(
        user["id"],
        user["role"],
        "PICKUP_ACCEPTED",
        "handover",
        handover_id,
        previous_status=handover["status"],
        new_status="COLLECTOR_ASSIGNED"
    )

    return jsonify({
        "success": True,
        "status": "COLLECTOR_ASSIGNED"
    })


@app.route("/api/collector/pickups/<handover_id>/start", methods=["POST"])
@login_required
@roles_required("COLLECTOR")
def start_trip(user, handover_id):

    collector = db_execute(
        """
        SELECT *
        FROM collectors
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    handover = db_execute(
        """
        SELECT *
        FROM handovers
        WHERE handover_id = %s
          AND assigned_collector_id = %s
        """,
        (handover_id, collector["id"]),
        fetchone=True
    )

    if not handover:
        return jsonify({
            "success": False,
            "error": "Assigned handover not found."
        }), 404

    db_execute(
        """
        UPDATE handovers
        SET status = 'TRAVELLING',
            updated_at = NOW()
        WHERE id = %s
        """,
        (handover["id"],),
        commit=True
    )

    return jsonify({
        "success": True,
        "status": "TRAVELLING"
    })


@app.route("/api/collector/pickups/<handover_id>/arrive", methods=["POST"])
@login_required
@roles_required("COLLECTOR")
def arrive_pickup(user, handover_id):

    collector = db_execute(
        """
        SELECT *
        FROM collectors
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    handover = db_execute(
        """
        SELECT *
        FROM handovers
        WHERE handover_id = %s
          AND assigned_collector_id = %s
        """,
        (handover_id, collector["id"]),
        fetchone=True
    )

    if not handover:
        return jsonify({
            "success": False,
            "error": "Assigned handover not found."
        }), 404

    db_execute(
        """
        UPDATE handovers
        SET status = 'ARRIVED',
            updated_at = NOW()
        WHERE id = %s
        """,
        (handover["id"],),
        commit=True
    )

    return jsonify({
        "success": True,
        "status": "ARRIVED"
    })


# ============================================================
# COLLECTOR LOCATION
# ============================================================

@app.route("/api/collector/location/sharing", methods=["POST"])
@login_required
@roles_required("COLLECTOR")
def location_sharing(user):

    data = request.get_json() or {}

    enabled = bool(data.get("enabled"))

    collector = db_execute(
        """
        SELECT collector_id
        FROM collectors
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    return jsonify({
        "success": True,
        "location_sharing": enabled,
        "collector_id": collector["collector_id"]
    })


@app.route("/api/collector/location", methods=["POST"])
@login_required
@roles_required("COLLECTOR")
def update_location(user):

    data = request.get_json() or {}

    latitude = data.get("latitude")
    longitude = data.get("longitude")

    if latitude is None or longitude is None:
        return jsonify({
            "success": False,
            "error": "Latitude and longitude are required."
        }), 400

    collector = db_execute(
        """
        SELECT *
        FROM collectors
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    db_execute(
        """
        INSERT INTO collector_locations
        (
            collector_id,
            latitude,
            longitude,
            accuracy,
            status,
            timestamp
        )
        VALUES (%s,%s,%s,%s,%s,NOW())
        """,
        (
            collector["id"],
            latitude,
            longitude,
            data.get("accuracy"),
            data.get("status", "AVAILABLE")
        ),
        commit=True
    )

    return jsonify({
        "success": True,
        "message": "Location updated."
    })


# ============================================================
# AGGREGATOR LIVE TRACKING
# ============================================================

@app.route("/api/aggregator/live-collectors")
@login_required
@roles_required("AGGREGATOR")
def live_collectors(user):

    rows = db_execute(
        """
        SELECT
            c.collector_id,
            u.full_name,
            u.phone,
            l.latitude,
            l.longitude,
            l.accuracy,
            l.status,
            l.timestamp AS last_updated
        FROM collectors c
        JOIN users u
          ON c.user_id = u.id
        LEFT JOIN LATERAL
        (
            SELECT *
            FROM collector_locations cl
            WHERE cl.collector_id = c.id
            ORDER BY cl.timestamp DESC
            LIMIT 1
        ) l ON TRUE
        ORDER BY u.full_name
        """,
        fetchall=True
    )

    return jsonify({
        "success": True,
        "collectors": rows
    })


@app.route("/api/aggregator/live-tracking")
@login_required
@roles_required("AGGREGATOR")
def live_tracking(user):

    rows = db_execute(
        """
        SELECT
            c.collector_id,
            u.full_name,
            u.phone,
            l.latitude,
            l.longitude,
            l.accuracy,
            l.status,
            l.timestamp AS last_updated
        FROM collectors c
        JOIN users u
          ON c.user_id = u.id
        LEFT JOIN LATERAL
        (
            SELECT *
            FROM collector_locations cl
            WHERE cl.collector_id = c.id
            ORDER BY cl.timestamp DESC
            LIMIT 1
        ) l ON TRUE
        """,
        fetchall=True
    )

    return jsonify({
        "success": True,
        "tracking": rows
    })


# ============================================================
# CREATE COLLECTION
# ============================================================

@app.route("/api/collection", methods=["POST"])
@login_required
@roles_required("COLLECTOR")
def create_collection(user):

    data = request.get_json() or {}

    collector = db_execute(
        """
        SELECT *
        FROM collectors
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    handover = db_execute(
        """
        SELECT *
        FROM handovers
        WHERE handover_id = %s
          AND assigned_collector_id = %s
        """,
        (
            data.get("handover_id"),
            collector["id"]
        ),
        fetchone=True
    )

    if not handover:
        return jsonify({
            "success": False,
            "error": "Assigned handover not found."
        }), 404

    image_hash = data.get("image_hash")

    if not image_hash:
        image_data = str({
            "handover_id": data.get("handover_id"),
            "product": data.get("product_name"),
            "weight": data.get("weight"),
            "timestamp": str(utc_now())
        })

        image_hash = hashlib.sha256(
            image_data.encode()
        ).hexdigest()

    duplicate = db_execute(
        """
        SELECT collection_id
        FROM collections
        WHERE image_hash = %s
        """,
        (image_hash,),
        fetchone=True
    )

    collection_id = generate_id("EW")

    conn = get_db()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO collections
            (
                collection_id,
                handover_id,
                customer_id,
                collector_id,
                brand_id,
                item_category,
                product_name,
                brand_name,
                quantity,
                declared_weight,
                collector_weight,
                latitude,
                longitude,
                gps_accuracy,
                image_hash,
                collection_photo,
                status
            )
            VALUES
            (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                collection_id,
                handover["id"],
                handover["customer_id"],
                collector["id"],
                handover["brand_id"],
                data.get("item_category", handover["product_category"]),
                data.get("product_name", handover["product_name"]),
                data.get("brand_name", handover["brand_name"]),
                data.get("quantity", handover["quantity"]),
                handover["estimated_weight"],
                data.get("weight", 0),
                data.get("latitude", handover["latitude"]),
                data.get("longitude", handover["longitude"]),
                data.get("gps_accuracy"),
                image_hash,
                data.get("photo"),
                "COLLECTED"
            )
        )

        collection = cur.fetchone()

        cur.execute(
            """
            UPDATE handovers
            SET status = 'COLLECTED',
                updated_at = NOW()
            WHERE id = %s
            """,
            (handover["id"],)
        )

        conn.commit()
        cur.close()

    except Exception as e:
        conn.rollback()

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    finally:
        conn.close()

    if duplicate:
        db_execute(
            """
            INSERT INTO anomaly_flags
            (
                collection_id,
                anomaly_type,
                severity,
                description
            )
            VALUES
            (%s,%s,%s,%s)
            """,
            (
                collection["id"],
                "DUPLICATE_IMAGE_HASH",
                "HIGH",
                f"Image hash already used by {duplicate['collection_id']}"
            ),
            commit=True
        )

    audit(
        user["id"],
        user["role"],
        "COLLECTION_CREATED",
        "collection",
        collection_id,
        new_status="COLLECTED"
    )

    return jsonify({
        "success": True,
        "collection_id": collection_id,
        "status": "COLLECTED",
        "image_hash": image_hash,
        "duplicate_flag": bool(duplicate)
    }), 201


# ============================================================
# COLLECTIONS
# ============================================================

@app.route("/api/collections")
@login_required
def collections_list(user):

    if user["role"] == "COLLECTOR":

        collector = db_execute(
            """
            SELECT id
            FROM collectors
            WHERE user_id = %s
            """,
            (user["id"],),
            fetchone=True
        )

        rows = db_execute(
            """
            SELECT *
            FROM collections
            WHERE collector_id = %s
            ORDER BY created_at DESC
            """,
            (collector["id"],),
            fetchall=True
        )

    elif user["role"] == "AGGREGATOR":

        rows = db_execute(
            """
            SELECT *
            FROM collections
            ORDER BY created_at DESC
            """,
            fetchall=True
        )

    elif user["role"] == "RECYCLER":

        recycler = db_execute(
            """
            SELECT id
            FROM recyclers
            WHERE user_id = %s
            """,
            (user["id"],),
            fetchone=True
        )

        rows = db_execute(
            """
            SELECT *
            FROM collections
            WHERE recycler_id = %s
            ORDER BY created_at DESC
            """,
            (recycler["id"],),
            fetchall=True
        )

    elif user["role"] == "BRAND_PRO":

        brand = db_execute(
            """
            SELECT id
            FROM brands
            WHERE user_id = %s
            """,
            (user["id"],),
            fetchone=True
        )

        rows = db_execute(
            """
            SELECT *
            FROM collections
            WHERE brand_id = %s
            ORDER BY created_at DESC
            """,
            (brand["id"],),
            fetchall=True
        )

    else:
        return jsonify({
            "success": False,
            "error": "Unauthorized."
        }), 403

    return jsonify({
        "success": True,
        "collections": rows
    })


# ============================================================
# COLLECTION DETAILS
# ============================================================

@app.route("/api/collection/<collection_id>")
@login_required
def collection_details(user, collection_id):

    collection = db_execute(
        """
        SELECT *
        FROM collections
        WHERE collection_id = %s
        """,
        (collection_id,),
        fetchone=True
    )

    if not collection:
        return jsonify({
            "success": False,
            "error": "Collection not found."
        }), 404

    return jsonify({
        "success": True,
        "collection": collection
    })


# ============================================================
# AGGREGATOR VERIFICATION
# ============================================================

@app.route("/api/collection/<collection_id>/verify", methods=["POST"])
@login_required
@roles_required("AGGREGATOR")
def verify_collection(user, collection_id):

    data = request.get_json() or {}

    aggregator = db_execute(
        """
        SELECT *
        FROM aggregators
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    collection = db_execute(
        """
        SELECT *
        FROM collections
        WHERE collection_id = %s
        """,
        (collection_id,),
        fetchone=True
    )

    if not collection:
        return jsonify({
            "success": False,
            "error": "Collection not found."
        }), 404

    verified_weight = float(data.get("verified_weight", 0))
    collector_weight = float(collection["collector_weight"] or 0)

    if collector_weight <= 0:
        return jsonify({
            "success": False,
            "error": "Invalid collector weight."
        }), 400

    difference = abs(
        verified_weight - collector_weight
    ) / collector_weight

    if difference > WEIGHT_TOLERANCE:

        db_execute(
            """
            INSERT INTO anomaly_flags
            (
                collection_id,
                anomaly_type,
                severity,
                description
            )
            VALUES (%s,%s,%s,%s)
            """,
            (
                collection["id"],
                "WEIGHT_MISMATCH",
                "HIGH",
                f"Collector weight {collector_weight} kg vs "
                f"aggregator weight {verified_weight} kg"
            ),
            commit=True
        )

        return jsonify({
            "success": False,
            "status": "FLAGGED",
            "error": "Weight variance exceeds 20% tolerance.",
            "collector_weight": collector_weight,
            "aggregator_weight": verified_weight
        }), 422

    db_execute(
        """
        UPDATE collections
        SET aggregator_id = %s,
            aggregator_weight = %s,
            status = 'AGGREGATOR_VERIFIED',
            updated_at = NOW()
        WHERE id = %s
        """,
        (
            aggregator["id"],
            verified_weight,
            collection["id"]
        ),
        commit=True
    )

    db_execute(
        """
        INSERT INTO verification_records
        (
            collection_id,
            verifier_user_id,
            verification_type,
            weight,
            status,
            notes
        )
        VALUES (%s,%s,%s,%s,%s,%s)
        """,
        (
            collection["id"],
            user["id"],
            "AGGREGATOR",
            verified_weight,
            "VERIFIED",
            data.get("notes")
        ),
        commit=True
    )

    audit(
        user["id"],
        user["role"],
        "COLLECTION_VERIFIED",
        "collection",
        collection_id,
        previous_status=collection["status"],
        new_status="AGGREGATOR_VERIFIED"
    )

    return jsonify({
        "success": True,
        "status": "AGGREGATOR_VERIFIED",
        "verified_weight": verified_weight
    })


# ============================================================
# RECYCLER INCOMING
# ============================================================

@app.route("/api/recycler/incoming")
@login_required
@roles_required("RECYCLER")
def recycler_incoming(user):

    rows = db_execute(
        """
        SELECT *
        FROM collections
        WHERE status = 'AGGREGATOR_VERIFIED'
        ORDER BY updated_at DESC
        """,
        fetchall=True
    )

    return jsonify({
        "success": True,
        "incoming": rows
    })


# ============================================================
# RECYCLER RECEIVE + EPR
# ============================================================

@app.route("/api/collection/<collection_id>/receive", methods=["POST"])
@login_required
@roles_required("RECYCLER")
def receive_collection(user, collection_id):

    data = request.get_json() or {}

    recycler = db_execute(
        """
        SELECT *
        FROM recyclers
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    collection = db_execute(
        """
        SELECT *
        FROM collections
        WHERE collection_id = %s
        """,
        (collection_id,),
        fetchone=True
    )

    if not collection:
        return jsonify({
            "success": False,
            "error": "Collection not found."
        }), 404

    if collection["status"] != "AGGREGATOR_VERIFIED":
        return jsonify({
            "success": False,
            "error": "Recycler receipt requires aggregator verification first."
        }), 409

    received_weight = float(data.get("received_weight", 0))
    aggregator_weight = float(collection["aggregator_weight"] or 0)

    if received_weight <= 0:
        return jsonify({
            "success": False,
            "error": "Invalid received weight."
        }), 400

    if aggregator_weight <= 0:
        return jsonify({
            "success": False,
            "error": "Aggregator weight is missing."
        }), 400

    difference = abs(
        received_weight - aggregator_weight
    ) / aggregator_weight

    if difference > WEIGHT_TOLERANCE:

        db_execute(
            """
            INSERT INTO anomaly_flags
            (
                collection_id,
                anomaly_type,
                severity,
                description
            )
            VALUES (%s,%s,%s,%s)
            """,
            (
                collection["id"],
                "RECYCLER_WEIGHT_MISMATCH",
                "HIGH",
                f"Aggregator weight {aggregator_weight} kg vs "
                f"recycler weight {received_weight} kg"
            ),
            commit=True
        )

        return jsonify({
            "success": False,
            "status": "FLAGGED",
            "error": "Recycler weight variance exceeds 20% tolerance."
        }), 422

    if not collection["image_hash"]:
        return jsonify({
            "success": False,
            "error": "Collection evidence is missing."
        }), 400

    conn = get_db()

    try:
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE collections
            SET recycler_id = %s,
                recycler_weight = %s,
                receiving_photo = %s,
                status = 'RECYCLER_RECEIVED',
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                recycler["id"],
                received_weight,
                data.get("receiving_photo"),
                collection["id"]
            )
        )

        epr_id = generate_id("EPR")

        cur.execute(
            """
            INSERT INTO epr_records
            (
                epr_id,
                collection_id,
                brand_id,
                recycler_id,
                verified_weight,
                material,
                status
            )
            VALUES (%s,%s,%s,%s,%s,%s,'EPR_VERIFIED')
            """,
            (
                epr_id,
                collection["id"],
                collection["brand_id"],
                recycler["id"],
                received_weight,
                collection["item_category"]
            )
        )

        cur.execute(
            """
            UPDATE collections
            SET status = 'EPR_VERIFIED'
            WHERE id = %s
            """,
            (collection["id"],)
        )

        conn.commit()
        cur.close()

    except Exception as e:
        conn.rollback()

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    finally:
        conn.close()

    # ========================================================
    # REWARDS
    # ========================================================

    collector = db_execute(
        """
        SELECT user_id
        FROM collectors
        WHERE id = %s
        """,
        (collection["collector_id"],),
        fetchone=True
    )

    customer = db_execute(
        """
        SELECT user_id
        FROM customers
        WHERE id = %s
        """,
        (collection["customer_id"],),
        fetchone=True
    )

    collector_points = round(
        received_weight * COLLECTOR_POINTS_PER_KG,
        2
    )

    customer_points = round(
        received_weight * CUSTOMER_POINTS_PER_KG,
        2
    )

    if collector:
        db_execute(
            """
            INSERT INTO reward_transactions
            (
                user_id,
                collection_id,
                role,
                points,
                transaction_type,
                description
            )
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (
                collector["user_id"],
                collection["id"],
                "COLLECTOR",
                collector_points,
                "CREDIT",
                f"Verified e-waste reward for {collection_id}"
            ),
            commit=True
        )

        notify(
            collector["user_id"],
            "Reward Credited",
            f"{collector_points} points credited for {collection_id}."
        )

    if customer:
        db_execute(
            """
            INSERT INTO reward_transactions
            (
                user_id,
                collection_id,
                role,
                points,
                transaction_type,
                description
            )
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (
                customer["user_id"],
                collection["id"],
                "USER",
                customer_points,
                "CREDIT",
                f"Responsible disposal reward for {collection_id}"
            ),
            commit=True
        )

        notify(
            customer["user_id"],
            "Reward Credited",
            f"{customer_points} points credited for your e-waste."
        )

    audit(
        user["id"],
        user["role"],
        "EPR_GENERATED",
        "epr",
        epr_id,
        previous_status="AGGREGATOR_VERIFIED",
        new_status="EPR_VERIFIED"
    )

    return jsonify({
        "success": True,
        "status": "EPR_VERIFIED",
        "epr_id": epr_id,
        "verified_weight": received_weight,
        "collector_points": collector_points,
        "customer_points": customer_points
    })


# ============================================================
# EPR
# ============================================================

@app.route("/api/epr/<epr_id>")
@login_required
def get_epr(user, epr_id):

    epr = db_execute(
        """
        SELECT
            e.*,
            b.brand_name,
            r.recycler_id
        FROM epr_records e
        LEFT JOIN brands b
          ON e.brand_id = b.id
        LEFT JOIN recyclers r
          ON e.recycler_id = r.id
        WHERE e.epr_id = %s
        """,
        (epr_id,),
        fetchone=True
    )

    if not epr:
        return jsonify({
            "success": False,
            "error": "EPR record not found."
        }), 404

    if user["role"] == "BRAND_PRO":

        brand = db_execute(
            """
            SELECT id
            FROM brands
            WHERE user_id = %s
            """,
            (user["id"],),
            fetchone=True
        )

        if not brand or epr["brand_id"] != brand["id"]:
            return jsonify({
                "success": False,
                "error": "Unauthorized EPR access."
            }), 403

    return jsonify({
        "success": True,
        "epr": epr
    })


# ============================================================
# BRAND DASHBOARD
# ============================================================

@app.route("/api/brand/dashboard")
@login_required
@roles_required("BRAND_PRO")
def brand_dashboard(user):

    brand = db_execute(
        """
        SELECT *
        FROM brands
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    if not brand:
        return jsonify({
            "success": False,
            "error": "Brand profile not found."
        }), 404

    verified = db_execute(
        """
        SELECT COALESCE(SUM(verified_weight), 0) AS total
        FROM epr_records
        WHERE brand_id = %s
          AND status = 'EPR_VERIFIED'
        """,
        (brand["id"],),
        fetchone=True
    )

    verified_weight = float(verified["total"] or 0)
    obligation = float(
        brand["epr_obligation"] or DEMO_EPR_OBLIGATION
    )

    remaining = max(
        obligation - verified_weight,
        0
    )

    compliance = (
        (verified_weight / obligation) * 100
        if obligation > 0 else 0
    )

    records = db_execute(
        """
        SELECT *
        FROM epr_records
        WHERE brand_id = %s
        ORDER BY created_at DESC
        """,
        (brand["id"],),
        fetchall=True
    )

    return jsonify({
        "success": True,
        "brand": {
            "brand_id": brand["brand_id"],
            "brand_name": brand["brand_name"],
            "organization_name": brand["organization_name"]
        },
        "epr": {
            "obligation": obligation,
            "verified": round(verified_weight, 2),
            "remaining": round(remaining, 2),
            "compliance_percentage": round(compliance, 2)
        },
        "records": records
    })


@app.route("/api/brand/epr")
@login_required
@roles_required("BRAND_PRO")
def brand_epr(user):

    brand = db_execute(
        """
        SELECT id
        FROM brands
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    rows = db_execute(
        """
        SELECT *
        FROM epr_records
        WHERE brand_id = %s
        ORDER BY created_at DESC
        """,
        (brand["id"],),
        fetchall=True
    )

    return jsonify({
        "success": True,
        "epr_records": rows
    })


# ============================================================
# EPR DOCUMENT METADATA
# ============================================================

@app.route("/api/brand/epr-documents", methods=["POST"])
@login_required
@roles_required("BRAND_PRO")
def create_epr_document(user):

    data = request.get_json() or {}

    brand = db_execute(
        """
        SELECT *
        FROM brands
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    if not brand:
        return jsonify({
            "success": False,
            "error": "Brand profile not found."
        }), 404

    verified = db_execute(
        """
        SELECT COALESCE(SUM(verified_weight),0) AS total
        FROM epr_records
        WHERE brand_id = %s
          AND status = 'EPR_VERIFIED'
        """,
        (brand["id"],),
        fetchone=True
    )

    verified_weight = float(verified["total"] or 0)
    obligation = float(brand["epr_obligation"] or 0)

    compliance = (
        verified_weight / obligation * 100
        if obligation > 0 else 0
    )

    document_id = generate_id("EPR-DOC")

    db_execute(
        """
        INSERT INTO epr_documents
        (
            document_id,
            brand_id,
            financial_year,
            epr_obligation,
            verified_weight,
            compliance_percentage,
            status
        )
        VALUES (%s,%s,%s,%s,%s,%s,'GENERATED')
        """,
        (
            document_id,
            brand["id"],
            data.get("financial_year", "2026-27"),
            obligation,
            verified_weight,
            compliance
        ),
        commit=True
    )

    audit(
        user["id"],
        user["role"],
        "EPR_DOCUMENT_CREATED",
        "epr_document",
        document_id,
        new_status="GENERATED"
    )

    return jsonify({
        "success": True,
        "document_id": document_id,
        "brand": brand["brand_name"],
        "verified_weight": verified_weight,
        "compliance_percentage": round(compliance, 2)
    }), 201


@app.route("/api/brand/epr-documents")
@login_required
@roles_required("BRAND_PRO")
def epr_documents(user):

    brand = db_execute(
        """
        SELECT id
        FROM brands
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    rows = db_execute(
        """
        SELECT *
        FROM epr_documents
        WHERE brand_id = %s
        ORDER BY created_at DESC
        """,
        (brand["id"],),
        fetchall=True
    )

    return jsonify({
        "success": True,
        "documents": rows
    })


# ============================================================
# REWARDS
# ============================================================

@app.route("/api/rewards/<int:user_id>")
@login_required
def rewards(user, user_id):

    # Users can only see their own rewards.
    # Aggregators/recyclers/brands do not get arbitrary access.

    if user["id"] != user_id:
        return jsonify({
            "success": False,
            "error": "Unauthorized."
        }), 403

    rows = db_execute(
        """
        SELECT *
        FROM reward_transactions
        WHERE user_id = %s
        ORDER BY created_at DESC
        """,
        (user_id,),
        fetchall=True
    )

    total = sum(
        float(row["points"] or 0)
        for row in rows
        if row["transaction_type"] == "CREDIT"
    )

    redeemed = sum(
        float(row["points"] or 0)
        for row in rows
        if row["transaction_type"] == "REDEEM"
    )

    available = total - redeemed

    return jsonify({
        "success": True,
        "points": {
            "total_earned": round(total, 2),
            "redeemed": round(redeemed, 2),
            "available": round(available, 2),
            "demo_cash_value": round(available * 0.10, 2)
        },
        "history": rows
    })


@app.route("/api/rewards/redeem", methods=["POST"])
@login_required
def redeem_reward(user):

    data = request.get_json() or {}

    points = float(data.get("points", 0))

    if points <= 0:
        return jsonify({
            "success": False,
            "error": "Invalid points."
        }), 400

    existing = db_execute(
        """
        SELECT COALESCE(SUM(
            CASE
                WHEN transaction_type = 'CREDIT'
                THEN points
                ELSE 0
            END
        ),0) -
        COALESCE(SUM(
            CASE
                WHEN transaction_type = 'REDEEM'
                THEN points
                ELSE 0
            END
        ),0) AS available
        FROM reward_transactions
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    available = float(existing["available"] or 0)

    if points > available:
        return jsonify({
            "success": False,
            "error": "Insufficient reward points."
        }), 400

    db_execute(
        """
        INSERT INTO reward_transactions
        (
            user_id,
            role,
            points,
            transaction_type,
            description
        )
        VALUES (%s,%s,%s,'REDEEM',%s)
        """,
        (
            user["id"],
            user["role"],
            points,
            f"Demo redemption via {data.get('method', 'UPI')}"
        ),
        commit=True
    )

    return jsonify({
        "success": True,
        "message": "Demo redemption recorded.",
        "points_redeemed": points,
        "method": data.get("method", "UPI"),
        "note": "No real money transfer is performed."
    })


# ============================================================
# NOTIFICATIONS
# ============================================================

@app.route("/api/notifications")
@login_required
def notifications(user):

    rows = db_execute(
        """
        SELECT *
        FROM notifications
        WHERE user_id = %s
        ORDER BY created_at DESC
        """,
        (user["id"],),
        fetchall=True
    )

    return jsonify({
        "success": True,
        "notifications": rows
    })


@app.route("/api/notifications/<int:notification_id>/read",
           methods=["POST"])
@login_required
def mark_notification_read(user, notification_id):

    db_execute(
        """
        UPDATE notifications
        SET is_read = TRUE
        WHERE id = %s
          AND user_id = %s
        """,
        (
            notification_id,
            user["id"]
        ),
        commit=True
    )

    return jsonify({
        "success": True
    })


# ============================================================
# AGGREGATOR DASHBOARD
# ============================================================

@app.route("/api/dashboard/aggregator")
@login_required
@roles_required("AGGREGATOR")
def aggregator_dashboard(user):

    stats = db_execute(
        """
        SELECT
            COUNT(*) FILTER (
                WHERE status = 'COLLECTED'
            ) AS pending_verification,

            COUNT(*) FILTER (
                WHERE status = 'AGGREGATOR_VERIFIED'
            ) AS verified_collections,

            COUNT(*) FILTER (
                WHERE status = 'IN_TRANSIT'
            ) AS material_in_transit,

            COALESCE(
                SUM(
                    COALESCE(aggregator_weight,0)
                ),
                0
            ) AS total_verified_weight
        FROM collections
        """,
        fetchone=True
    )

    collectors = db_execute(
        """
        SELECT COUNT(*) AS total
        FROM collectors
        """,
        fetchone=True
    )

    return jsonify({
        "success": True,
        "stats": {
            "pending_verification": stats["pending_verification"],
            "verified_collections": stats["verified_collections"],
            "material_in_transit": stats["material_in_transit"],
            "total_verified_weight": float(
                stats["total_verified_weight"] or 0
            ),
            "active_collectors": collectors["total"]
        }
    })


# ============================================================
# COLLECTOR DASHBOARD
# ============================================================

@app.route("/api/dashboard/collector")
@login_required
@roles_required("COLLECTOR")
def collector_dashboard(user):

    collector = db_execute(
        """
        SELECT *
        FROM collectors
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    stats = db_execute(
        """
        SELECT
            COUNT(*) AS total_collections,
            COALESCE(
                SUM(recycler_weight),
                0
            ) AS verified_weight
        FROM collections
        WHERE collector_id = %s
        """,
        (collector["id"],),
        fetchone=True
    )

    reward = db_execute(
        """
        SELECT COALESCE(
            SUM(
                CASE
                    WHEN transaction_type = 'CREDIT'
                    THEN points
                    ELSE -points
                END
            ),0
        ) AS points
        FROM reward_transactions
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    return jsonify({
        "success": True,
        "stats": {
            "total_collections": stats["total_collections"],
            "verified_weight": float(
                stats["verified_weight"] or 0
            ),
            "reward_points": float(
                reward["points"] or 0
            )
        }
    })


# ============================================================
# CUSTOMER DASHBOARD
# ============================================================

@app.route("/api/dashboard/user")
@login_required
@roles_required("USER")
def user_dashboard(user):

    customer = db_execute(
        """
        SELECT *
        FROM customers
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    stats = db_execute(
        """
        SELECT
            COUNT(*) AS handovers
        FROM handovers
        WHERE customer_id = %s
        """,
        (customer["id"],),
        fetchone=True
    )

    weight = db_execute(
        """
        SELECT COALESCE(
            SUM(recycler_weight),0
        ) AS verified
        FROM collections
        WHERE customer_id = %s
          AND status = 'EPR_VERIFIED'
        """,
        (customer["id"],),
        fetchone=True
    )

    rewards_data = db_execute(
        """
        SELECT COALESCE(
            SUM(
                CASE
                    WHEN transaction_type = 'CREDIT'
                    THEN points
                    ELSE -points
                END
            ),0
        ) AS points
        FROM reward_transactions
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    return jsonify({
        "success": True,
        "stats": {
            "handovers": stats["handovers"],
            "verified_weight": float(
                weight["verified"] or 0
            ),
            "reward_points": float(
                rewards_data["points"] or 0
            )
        }
    })


# ============================================================
# RECYCLER DASHBOARD
# ============================================================

@app.route("/api/dashboard/recycler")
@login_required
@roles_required("RECYCLER")
def recycler_dashboard(user):

    recycler = db_execute(
        """
        SELECT id
        FROM recyclers
        WHERE user_id = %s
        """,
        (user["id"],),
        fetchone=True
    )

    stats = db_execute(
        """
        SELECT
            COUNT(*) FILTER (
                WHERE status = 'AGGREGATOR_VERIFIED'
            ) AS pending_receipts,

            COUNT(*) FILTER (
                WHERE status = 'EPR_VERIFIED'
            ) AS verified_records,

            COALESCE(
                SUM(recycler_weight),
                0
            ) AS received_weight
        FROM collections
        WHERE recycler_id = %s
           OR (
                recycler_id IS NULL
                AND status = 'AGGREGATOR_VERIFIED'
           )
        """,
        (recycler["id"],),
        fetchone=True
    )

    return jsonify({
        "success": True,
        "stats": {
            "pending_receipts": stats["pending_receipts"],
            "verified_records": stats["verified_records"],
            "received_weight": float(
                stats["received_weight"] or 0
            )
        }
    })


# ============================================================
# GENERIC DASHBOARD ROUTER
# ============================================================

@app.route("/api/dashboard")
@login_required
def dashboard(user):

    role = user["role"]

    if role == "USER":
        return user_dashboard(user)

    if role == "COLLECTOR":
        return collector_dashboard(user)

    if role == "AGGREGATOR":
        return aggregator_dashboard(user)

    if role == "RECYCLER":
        return recycler_dashboard(user)

    if role == "BRAND_PRO":
        return brand_dashboard(user)

    return jsonify({
        "success": False,
        "error": "Unknown role."
    }), 403


# ============================================================
# ROOT FRONTEND
# ============================================================

@app.route("/")
def index():

    # Supports a simple root index.html setup.
    if os.path.exists("index.html"):
        return send_from_directory(".", "index.html")

    if os.path.exists(
        os.path.join(app.static_folder or "", "index.html")
    ):
        return send_from_directory(
            app.static_folder,
            "index.html"
        )

    return jsonify({
        "message": "E-Waste EPR Platform API is running."
    })


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    if request.path.startswith("/api/"):
        return jsonify({
            "success": False,
            "error": "API endpoint not found."
        }), 404

    return jsonify({
        "success": False,
        "error": "Page not found."
    }), 404


@app.errorhandler(500)
def internal_error(error):

    return jsonify({
        "success": False,
        "error": "Internal server error."
    }), 500


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )
