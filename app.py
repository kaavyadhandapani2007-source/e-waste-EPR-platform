import os
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    jwt_required,
    get_jwt,
)

# ============================================================
# APP CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(BASE_DIR, "ewaste.db")
)

# Render / PostgreSQL compatibility
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql://",
        1
    )

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = os.getenv(
    "JWT_SECRET_KEY",
    "change-this-demo-secret"
)

db = SQLAlchemy(app)
jwt = JWTManager(app)

# ============================================================
# REWARD CONFIGURATION
# ============================================================

# NOTE:
# Reward points are NOT EPR credits.
# EPR quantity is generated only after recycler confirmation.

POINT_VALUE = 0.10

CUSTOMER_POINTS_PER_KG = 5
COLLECTOR_POINTS_PER_KG = 10

MIN_WITHDRAW_POINTS = 100


# ============================================================
# DATABASE MODELS
# ============================================================

class User(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.String(40),
        unique=True,
        nullable=False
    )

    name = db.Column(
        db.String(120),
        nullable=False
    )

    role = db.Column(
        db.String(30),
        nullable=False
    )

    phone = db.Column(
        db.String(30)
    )

    active = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)
    )


class CustomerHandover(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    handover_id = db.Column(
        db.String(40),
        unique=True,
        nullable=False
    )

    customer_id = db.Column(
        db.String(40),
        nullable=False
    )

    collector_id = db.Column(
        db.String(40),
        nullable=False
    )

    phone = db.Column(
        db.String(30)
    )

    location = db.Column(
        db.String(255)
    )

    product = db.Column(
        db.String(120),
        nullable=False
    )

    approximate_weight = db.Column(
        db.Float,
        default=0
    )

    serial_number = db.Column(
        db.String(120)
    )

    photo_hash = db.Column(
        db.String(64)
    )

    status = db.Column(
        db.String(40),
        default="HANDED_OVER"
    )

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)
    )


class Collection(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    collection_id = db.Column(
        db.String(40),
        unique=True,
        nullable=False
    )

    handover_id = db.Column(
        db.String(40),
        nullable=False
    )

    collector_id = db.Column(
        db.String(40),
        nullable=False
    )

    aggregator_id = db.Column(
        db.String(40)
    )

    recycler_id = db.Column(
        db.String(40)
    )

    collector_weight = db.Column(
        db.Float,
        default=0
    )

    verified_weight = db.Column(
        db.Float
    )

    recycler_weight = db.Column(
        db.Float
    )

    gps = db.Column(
        db.String(100)
    )

    photo_hash = db.Column(
        db.String(64)
    )

    status = db.Column(
        db.String(40),
        default="COLLECTED"
    )

    anomaly = db.Column(
        db.Boolean,
        default=False
    )

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)
    )


class EPRRecord(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    epr_id = db.Column(
        db.String(40),
        unique=True,
        nullable=False
    )

    collection_id = db.Column(
        db.String(40),
        nullable=False
    )

    brand = db.Column(
        db.String(120),
        nullable=False
    )

    verified_weight = db.Column(
        db.Float,
        nullable=False
    )

    status = db.Column(
        db.String(30),
        default="VERIFIED"
    )

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)
    )


class RewardTransaction(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    transaction_id = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )

    user_id = db.Column(
        db.String(40),
        nullable=False
    )

    points = db.Column(
        db.Integer,
        nullable=False
    )

    transaction_type = db.Column(
        db.String(30),
        nullable=False
    )

    reference_id = db.Column(
        db.String(50)
    )

    description = db.Column(
        db.String(255)
    )

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)
    )


class Withdrawal(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    withdrawal_id = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )

    user_id = db.Column(
        db.String(40),
        nullable=False
    )

    points = db.Column(
        db.Integer,
        nullable=False
    )

    amount = db.Column(
        db.Float,
        nullable=False
    )

    upi_id = db.Column(
        db.String(120),
        nullable=False
    )

    status = db.Column(
        db.String(20),
        default="PENDING"
    )

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)
    )


class AuditLog(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    actor_id = db.Column(
        db.String(40),
        nullable=False
    )

    action = db.Column(
        db.String(100),
        nullable=False
    )

    entity_type = db.Column(
        db.String(50)
    )

    entity_id = db.Column(
        db.String(50)
    )

    details = db.Column(
        db.Text
    )

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)
    )


class AnomalyFlag(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    anomaly_id = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )

    collection_id = db.Column(
        db.String(40),
        nullable=False
    )

    reason = db.Column(
        db.String(255),
        nullable=False
    )

    severity = db.Column(
        db.String(20),
        default="MEDIUM"
    )

    resolved = db.Column(
        db.Boolean,
        default=False
    )

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc)
    )


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def iso(dt=None):
    return (
        dt or datetime.now(timezone.utc)
    ).isoformat()


def get_user(user_id):
    return User.query.filter_by(
        user_id=user_id
    ).first()


def make_id(prefix, model, field, start=1001):

    number = start
    column = getattr(model, field)

    while model.query.filter(
        column == f"{prefix}-{number}"
    ).first():

        number += 1

    return f"{prefix}-{number}"


def audit(
    actor,
    action,
    entity_type="",
    entity_id="",
    details=""
):

    db.session.add(
        AuditLog(
            actor_id=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details
        )
    )


def current_user():

    claims = get_jwt()

    return get_user(
        claims.get("user_id")
    )


def role_required(*roles):

    def decorator(function):

        @wraps(function)
        @jwt_required()
        def wrapper(*args, **kwargs):

            user = current_user()

            if not user or not user.active:

                return jsonify({
                    "error":
                    "User is inactive or not found"
                }), 403

            if user.role not in roles:

                return jsonify({
                    "error":
                    "Access denied",
                    "message":
                    "Required role: " +
                    ", ".join(roles)
                }), 403

            return function(
                *args,
                **kwargs
            )

        return wrapper

    return decorator


def rewards_for(user_id):

    transactions = RewardTransaction.query.filter_by(
        user_id=user_id
    ).all()

    points = sum(
        transaction.points
        for transaction in transactions
    )

    return {
        "points": points,
        "cash": round(
            points * POINT_VALUE,
            2
        )
    }


def user_json(user):

    return {
        "user_id": user.user_id,
        "name": user.name,
        "role": user.role,
        "phone": user.phone,
        "active": user.active,
        "created_at": iso(user.created_at)
    }


def collection_json(collection):

    return {
        "collection_id":
            collection.collection_id,

        "handover_id":
            collection.handover_id,

        "collector_id":
            collection.collector_id,

        "aggregator_id":
            collection.aggregator_id,

        "recycler_id":
            collection.recycler_id,

        "collector_weight":
            collection.collector_weight,

        "verified_weight":
            collection.verified_weight,

        "recycler_weight":
            collection.recycler_weight,

        "gps":
            collection.gps,

        "photo_hash":
            collection.photo_hash,

        "status":
            collection.status,

        "anomaly":
            collection.anomaly,

        "created_at":
            iso(collection.created_at)
    }


def positive_number(value):

    try:

        value = float(value)

        if value <= 0:
            return False, 0

        return True, value

    except (
        TypeError,
        ValueError
    ):

        return False, 0


# ============================================================
# DEMO USERS
# ============================================================

def seed_users():

    demo_users = [

        (
            "CUS-1001",
            "Demo Customer",
            "CUSTOMER",
            "9000000001"
        ),

        (
            "COL-2001",
            "Demo Collector",
            "COLLECTOR",
            "9000000002"
        ),

        (
            "AGG-3001",
            "Demo Aggregator",
            "AGGREGATOR",
            "9000000003"
        ),

        (
            "REC-4001",
            "Demo Recycler",
            "RECYCLER",
            "9000000004"
        ),

        (
            "BRD-5001",
            "ECOGEN Electronics",
            "BRAND",
            "9000000005"
        ),

        (
            "ADM-0001",
            "System Supervisor",
            "ADMIN",
            "9000000006"
        )
    ]

    for (
        user_id,
        name,
        role,
        phone
    ) in demo_users:

        if not get_user(user_id):

            db.session.add(
                User(
                    user_id=user_id,
                    name=name,
                    role=role,
                    phone=phone,
                    active=True
                )
            )

    db.session.commit()


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

with app.app_context():

    db.create_all()

    seed_users()


# ============================================================
# BASIC ROUTES
# ============================================================

@app.route("/")
def home():

    return send_from_directory(
        BASE_DIR,
        "index.html"
    )


@app.route("/health")
def health():

    return jsonify({
        "status": "online",
        "service": "e-waste-epr-platform"
    })


@app.route("/api/status")
def api_status():

    return jsonify({

        "status": "online",

        "database": "connected",

        "reward_point_value":
            POINT_VALUE,

        "roles": [
            "CUSTOMER",
            "COLLECTOR",
            "AGGREGATOR",
            "RECYCLER",
            "BRAND",
            "ADMIN"
        ]
    })


# ============================================================
# AUTHENTICATION
# ============================================================

@app.route(
    "/api/auth/login",
    methods=["POST"]
)
def login():

    data = request.get_json(
        silent=True
    ) or {}

    role = str(
        data.get("role", "")
    ).strip().upper()

    user_id = str(
        data.get("user_id", "")
    ).strip().upper()

    allowed_roles = {

        "CUSTOMER",
        "COLLECTOR",
        "AGGREGATOR",
        "RECYCLER",
        "BRAND",
        "ADMIN"
    }

    if role not in allowed_roles:

        return jsonify({
            "error":
            "Invalid role"
        }), 400

    if not user_id:

        return jsonify({
            "error":
            "ID is required"
        }), 400

    user = get_user(user_id)

    if not user:

        return jsonify({
            "error":
            "ID not found"
        }), 404

    if not user.active:

        return jsonify({
            "error":
            "This account is inactive"
        }), 403

    # --------------------------------------------------------
    # IMPORTANT SECURITY CHECK
    # The entered ID must belong to the selected role.
    # --------------------------------------------------------

    if user.role != role:

        return jsonify({

            "error":
            "Role mismatch",

            "message":
            f"{user_id} belongs to "
            f"{user.role}, not {role}"
        }), 403

    token = create_access_token(

        identity=user.user_id,

        additional_claims={

            "user_id":
                user.user_id,

            "role":
                user.role
        }
    )

    audit(
        user.user_id,
        "LOGIN",
        "USER",
        user.user_id,
        "Successful demo login"
    )

    db.session.commit()

    return jsonify({

        "message":
            "Login successful",

        "access_token":
            token,

        "user":
            user_json(user)
    })


@app.route("/api/me")
@jwt_required()
def me():

    user = current_user()

    if not user:

        return jsonify({
            "error":
            "User not found"
        }), 404

    return jsonify({

        "user":
            user_json(user),

        "rewards":
            rewards_for(
                user.user_id
            )
    })


# ============================================================
# CUSTOMER HANDOVER
# ============================================================

@app.route(
    "/api/handover",
    methods=["POST"]
)
@role_required("CUSTOMER")
def create_handover():

    user = current_user()

    data = request.get_json(
        silent=True
    ) or {}

    product = str(
        data.get("product", "")
    ).strip()

    collector_id = str(
        data.get("collector_id", "")
    ).strip().upper()

    if not product:

        return jsonify({
            "error":
            "Product is required"
        }), 400

    collector = get_user(
        collector_id
    )

    if (
        not collector
        or collector.role != "COLLECTOR"
        or not collector.active
    ):

        return jsonify({
            "error":
            "Invalid or inactive collector ID"
        }), 400

    valid, weight = positive_number(
        data.get("approximate_weight")
    )

    if not valid:

        return jsonify({
            "error":
            "Weight must be greater than zero"
        }), 400

    handover_id = make_id(
        "HO",
        CustomerHandover,
        "handover_id"
    )

    handover = CustomerHandover(

        handover_id=handover_id,

        customer_id=user.user_id,

        collector_id=collector_id,

        phone=
            data.get("phone")
            or user.phone,

        location=
            data.get("location", ""),

        product=product,

        approximate_weight=
            weight,

        serial_number=
            data.get(
                "serial_number",
                ""
            ),

        photo_hash=
            data.get(
                "photo_hash",
                ""
            ),

        status=
            "HANDED_OVER"
    )

    db.session.add(handover)

    audit(
        user.user_id,
        "CREATE_HANDOVER",
        "HANDOVER",
        handover_id,
        product
    )

    db.session.commit()

    return jsonify({

        "message":
            "Handover created",

        "handover": {

            "handover_id":
                handover_id,

            "customer_id":
                user.user_id,

            "collector_id":
                collector_id,

            "status":
                handover.status
        }
    }), 201


@app.route("/api/handovers")
@jwt_required()
def get_handovers():

    user = current_user()

    query = CustomerHandover.query

    if user.role == "CUSTOMER":

        query = query.filter_by(
            customer_id=user.user_id
        )

    elif user.role == "COLLECTOR":

        query = query.filter_by(
            collector_id=user.user_id
        )

    rows = query.order_by(
        CustomerHandover.id.desc()
    ).limit(200).all()

    return jsonify([

        {
            "handover_id":
                h.handover_id,

            "customer_id":
                h.customer_id,

            "collector_id":
                h.collector_id,

            "product":
                h.product,

            "approximate_weight":
                h.approximate_weight,

            "serial_number":
                h.serial_number,

            "location":
                h.location,

            "status":
                h.status,

            "created_at":
                iso(h.created_at)
        }

        for h in rows
    ])


# ============================================================
# COLLECTOR COLLECTION
# ============================================================

@app.route(
    "/api/collection",
    methods=["POST"]
)
@role_required("COLLECTOR")
def create_collection():

    user = current_user()

    data = request.get_json(
        silent=True
    ) or {}

    handover_id = str(
        data.get("handover_id", "")
    ).strip().upper()

    handover = CustomerHandover.query.filter_by(
        handover_id=handover_id
    ).first()

    if not handover:

        return jsonify({
            "error":
            "Handover not found"
        }), 404

    if handover.collector_id != user.user_id:

        return jsonify({
            "error":
            "This handover is assigned to another collector"
        }), 403

    valid, weight = positive_number(
        data.get("weight")
    )

    if not valid:

        return jsonify({
            "error":
            "Weight must be greater than zero"
        }), 400

    image_hash = str(
        data.get(
            "image_hash",
            ""
        )
    ).strip()

    duplicate = False

    if image_hash:

        duplicate = (
            Collection.query.filter_by(
                photo_hash=image_hash
            ).first()
            is not None
        )

    collection_id = make_id(
        "COLL",
        Collection,
        "collection_id"
    )

    collection = Collection(

        collection_id=
            collection_id,

        handover_id=
            handover_id,

        collector_id=
            user.user_id,

        collector_weight=
            weight,

        gps=
            data.get(
                "gps",
                ""
            ),

        photo_hash=
            image_hash,

        status=
            "COLLECTED",

        anomaly=
            duplicate
    )

    db.session.add(
        collection
    )

    handover.status = "COLLECTED"

    if duplicate:

        anomaly_id = make_id(
            "ANOM",
            AnomalyFlag,
            "anomaly_id"
        )

        db.session.add(
            AnomalyFlag(

                anomaly_id=
                    anomaly_id,

                collection_id=
                    collection_id,

                reason=
                    "Duplicate image hash detected",

                severity=
                    "HIGH"
            )
        )

        audit(
            user.user_id,
            "ANOMALY_FLAGGED",
            "COLLECTION",
            collection_id,
            "Duplicate image hash"
        )

    audit(
        user.user_id,
        "CREATE_COLLECTION",
        "COLLECTION",
        collection_id,
        f"{weight} kg"
    )

    db.session.commit()

    return jsonify({

        "message":
            "Collection recorded",

        "collection":
            collection_json(
                collection
            )
    }), 201


@app.route("/api/collections")
@jwt_required()
def get_collections():

    user = current_user()

    query = Collection.query

    if user.role == "COLLECTOR":

        query = query.filter_by(
            collector_id=user.user_id
        )

    elif user.role == "AGGREGATOR":

        query = query.filter(
            (
                Collection.aggregator_id
                == user.user_id
            )
            |
            (
                Collection.aggregator_id
                .is_(None)
            )
        )

    elif user.role == "RECYCLER":

        query = query.filter(
            (
                Collection.recycler_id
                == user.user_id
            )
            |
            (
                Collection.recycler_id
                .is_(None)
            )
        )

    rows = query.order_by(
        Collection.id.desc()
    ).limit(300).all()

    return jsonify([
        collection_json(c)
        for c in rows
    ])


@app.route(
    "/api/collection/<collection_id>"
)
@jwt_required()
def get_collection(collection_id):

    collection = Collection.query.filter_by(
        collection_id=
            collection_id.upper()
    ).first()

    if not collection:

        return jsonify({
            "error":
            "Collection not found"
        }), 404

    return jsonify(
        collection_json(
            collection
        )
    )


# ============================================================
# AGGREGATOR VERIFICATION
# ============================================================

@app.route(
    "/api/collection/<collection_id>/verify",
    methods=["POST"]
)
@role_required("AGGREGATOR")
def verify_collection(collection_id):

    user = current_user()

    collection = Collection.query.filter_by(
        collection_id=
            collection_id.upper()
    ).first()

    if not collection:

        return jsonify({
            "error":
            "Collection not found"
        }), 404

    if collection.status not in {
        "COLLECTED",
        "AGGREGATOR_VERIFIED"
    }:

        return jsonify({
            "error":
            f"Cannot verify status "
            f"{collection.status}"
        }), 400

    data = request.get_json(
        silent=True
    ) or {}

    valid, verified_weight = positive_number(
        data.get("verified_weight")
    )

    if not valid:

        return jsonify({
            "error":
            "Verified weight must be greater than zero"
        }), 400

    # --------------------------------------------------------
    # Weight anomaly detection
    # --------------------------------------------------------

    if collection.collector_weight > 0:

        difference = (
            abs(
                verified_weight
                - collection.collector_weight
            )
            /
            collection.collector_weight
        )

        if difference > 0.20:

            collection.anomaly = True

            anomaly_id = make_id(
                "ANOM",
                AnomalyFlag,
                "anomaly_id"
            )

            db.session.add(
                AnomalyFlag(

                    anomaly_id=
                        anomaly_id,

                    collection_id=
                        collection.collection_id,

                    reason=
                        "Aggregator weight differs by more than 20% from collector weight",

                    severity=
                        "MEDIUM"
                )
            )

            audit(
                user.user_id,
                "WEIGHT_ANOMALY",
                "COLLECTION",
                collection.collection_id,
                (
                    f"Collector="
                    f"{collection.collector_weight}, "
                    f"Aggregator="
                    f"{verified_weight}"
                )
            )

    collection.aggregator_id = user.user_id

    collection.verified_weight = (
        verified_weight
    )

    collection.status = (
        "AGGREGATOR_VERIFIED"
    )

    handover = CustomerHandover.query.filter_by(
        handover_id=
            collection.handover_id
    ).first()

    if handover:

        handover.status = (
            "AGGREGATOR_VERIFIED"
        )

    audit(
        user.user_id,
        "VERIFY_COLLECTION",
        "COLLECTION",
        collection.collection_id,
        f"{verified_weight} kg"
    )

    db.session.commit()

    return jsonify({

        "message":
            "Aggregator verification completed",

        "collection":
            collection_json(
                collection
            )
    })


# ============================================================
# RECYCLER RECEIPT + EPR + REWARDS
# ============================================================

@app.route(
    "/api/collection/<collection_id>/receive",
    methods=["POST"]
)
@role_required("RECYCLER")
def receive_collection(collection_id):

    user = current_user()

    collection = Collection.query.filter_by(
        collection_id=
            collection_id.upper()
    ).first()

    if not collection:

        return jsonify({
            "error":
            "Collection not found"
        }), 404

    # EPR cannot be generated before
    # aggregator verification.

    if collection.status != (
        "AGGREGATOR_VERIFIED"
    ):

        return jsonify({
            "error":
            "Recycler receipt requires aggregator verification first"
        }), 400

    data = request.get_json(
        silent=True
    ) or {}

    valid, recycler_weight = positive_number(
        data.get("recycler_weight")
    )

    if not valid:

        return jsonify({
            "error":
            "Recycler weight must be greater than zero"
        }), 400

    collection.recycler_id = user.user_id

    collection.recycler_weight = (
        recycler_weight
    )

    collection.status = (
        "RECYCLER_RECEIVED"
    )

    handover = CustomerHandover.query.filter_by(
        handover_id=
            collection.handover_id
    ).first()

    if handover:

        handover.status = (
            "RECYCLER_RECEIVED"
        )

    # --------------------------------------------------------
    # EPR record
    # --------------------------------------------------------

    epr_id = make_id(
        "EPR",
        EPRRecord,
        "epr_id"
    )

    epr = EPRRecord(

        epr_id=
            epr_id,

        collection_id=
            collection.collection_id,

        brand=
            "ECOGEN Electronics",

        verified_weight=
            recycler_weight,

        status=
            "VERIFIED"
    )

    db.session.add(epr)

    # --------------------------------------------------------
    # Reward calculation
    # --------------------------------------------------------

    customer_points = round(
        recycler_weight
        * CUSTOMER_POINTS_PER_KG
    )

    collector_points = round(
        recycler_weight
        * COLLECTOR_POINTS_PER_KG
    )

    if handover:

        db.session.add(
            RewardTransaction(

                transaction_id=
                    make_id(
                        "RWD",
                        RewardTransaction,
                        "transaction_id"
                    ),

                user_id=
                    handover.customer_id,

                points=
                    customer_points,

                transaction_type=
                    "CREDIT",

                reference_id=
                    collection.collection_id,

                description=
                    (
                        "Verified e-waste "
                        "reward for "
                        f"{recycler_weight} kg"
                    )
            )
        )

    db.session.add(
        RewardTransaction(

            transaction_id=
                make_id(
                    "RWD",
                    RewardTransaction,
                    "transaction_id"
                ),

            user_id=
                collection.collector_id,

            points=
                collector_points,

            transaction_type=
                "CREDIT",

            reference_id=
                collection.collection_id,

            description=
                (
                    "Collector reward for "
                    f"{recycler_weight} kg"
                )
        )
    )

    audit(
        user.user_id,
        "RECYCLER_RECEIPT",
        "COLLECTION",
        collection.collection_id,
        f"{recycler_weight} kg"
    )

    audit(
        user.user_id,
        "EPR_GENERATED",
        "EPR",
        epr_id,
        f"{recycler_weight} kg"
    )

    db.session.commit()

    return jsonify({

        "message":
            (
                "Recycler receipt confirmed. "
                "EPR generated and rewards credited."
            ),

        "epr": {

            "epr_id":
                epr.epr_id,

            "collection_id":
                epr.collection_id,

            "brand":
                epr.brand,

            "verified_weight":
                epr.verified_weight,

            "status":
                epr.status
        },

        "rewards": {

            "customer_points":
                customer_points,

            "collector_points":
                collector_points
        },

        "collection":
            collection_json(
                collection
            )
    })


@app.route(
    "/api/epr/<epr_id>"
)
@jwt_required()
def get_epr(epr_id):

    epr = EPRRecord.query.filter_by(
        epr_id=
            epr_id.upper()
    ).first()

    if not epr:

        return jsonify({
            "error":
            "EPR record not found"
        }), 404

    return jsonify({

        "epr_id":
            epr.epr_id,

        "collection_id":
            epr.collection_id,

        "brand":
            epr.brand,

        "verified_weight":
            epr.verified_weight,

        "status":
            epr.status,

        "created_at":
            iso(epr.created_at)
    })


# ============================================================
# REWARDS
# ============================================================

@app.route(
    "/api/rewards/<user_id>"
)
@jwt_required()
def get_rewards(user_id):

    requester = current_user()

    target = get_user(
        user_id.upper()
    )

    if not target:

        return jsonify({
            "error":
            "User not found"
        }), 404

    if (
        requester.role != "ADMIN"
        and requester.user_id != target.user_id
    ):

        return jsonify({
            "error":
            "You can only view your own rewards"
        }), 403

    transactions = RewardTransaction.query.filter_by(
        user_id=
            target.user_id
    ).order_by(
        RewardTransaction.id.desc()
    ).limit(100).all()

    return jsonify({

        "user_id":
            target.user_id,

        "role":
            target.role,

        "balance":
            rewards_for(
                target.user_id
            ),

        "transactions": [

            {
                "transaction_id":
                    transaction.transaction_id,

                "points":
                    transaction.points,

                "type":
                    transaction.transaction_type,

                "reference_id":
                    transaction.reference_id,

                "description":
                    transaction.description,

                "created_at":
                    iso(
                        transaction.created_at
                    )
            }

            for transaction in transactions
        ]
    })


# ============================================================
# WITHDRAWAL REQUEST
# ============================================================

@app.route(
    "/api/withdraw",
    methods=["POST"]
)
@role_required(
    "CUSTOMER",
    "COLLECTOR"
)
def request_withdrawal():

    user = current_user()

    data = request.get_json(
        silent=True
    ) or {}

    try:

        points = int(
            data.get(
                "points",
                0
            )
        )

    except (
        TypeError,
        ValueError
    ):

        return jsonify({
            "error":
            "Points must be a number"
        }), 400

    upi_id = str(
        data.get(
            "upi_id",
            ""
        )
    ).strip()

    if points < MIN_WITHDRAW_POINTS:

        return jsonify({
            "error":
            (
                "Minimum withdrawal is "
                f"{MIN_WITHDRAW_POINTS} points"
            )
        }), 400

    if not upi_id or "@" not in upi_id:

        return jsonify({
            "error":
            "Enter a valid demo UPI ID"
        }), 400

    balance = rewards_for(
        user.user_id
    )["points"]

    pending = sum(

        withdrawal.points

        for withdrawal
        in Withdrawal.query.filter_by(
            user_id=user.user_id,
            status="PENDING"
        ).all()
    )

    available = balance - pending

    if points > available:

        return jsonify({
            "error":
            "Insufficient available reward points"
        }), 400

    withdrawal_id = make_id(
        "WD",
        Withdrawal,
        "withdrawal_id"
    )

    amount = round(
        points * POINT_VALUE,
        2
    )

    withdrawal = Withdrawal(

        withdrawal_id=
            withdrawal_id,

        user_id=
            user.user_id,

        points=
            points,

        amount=
            amount,

        upi_id=
            upi_id,

        status=
            "PENDING"
    )

    db.session.add(
        withdrawal
    )

    audit(
        user.user_id,
        "WITHDRAWAL_REQUEST",
        "WITHDRAWAL",
        withdrawal_id,
        (
            f"{points} points / "
            f"₹{amount}"
        )
    )

    db.session.commit()

    return jsonify({

        "message":
            "Withdrawal request submitted for admin approval",

        "withdrawal": {

            "withdrawal_id":
                withdrawal_id,

            "points":
                points,

            "amount":
                amount,

            "upi_id":
                upi_id,

            "status":
                "PENDING"
        },

        "note":
            (
                "Prototype ledger only; "
                "no real payment is transferred."
            )
    }), 201


@app.route("/api/withdrawals")
@jwt_required()
def get_withdrawals():

    user = current_user()

    if user.role == "ADMIN":

        rows = Withdrawal.query.order_by(
            Withdrawal.id.desc()
        ).limit(200).all()

    else:

        rows = Withdrawal.query.filter_by(
            user_id=user.user_id
        ).order_by(
            Withdrawal.id.desc()
        ).limit(100).all()

    return jsonify([

        {
            "withdrawal_id":
                w.withdrawal_id,

            "user_id":
                w.user_id,

            "points":
                w.points,

            "amount":
                w.amount,

            "upi_id":
                w.upi_id,

            "status":
                w.status,

            "created_at":
                iso(w.created_at)
        }

        for w in rows
    ])


# ============================================================
# ADMIN WITHDRAWAL APPROVAL
# ============================================================

@app.route(
    "/api/admin/withdrawals/<withdrawal_id>/approve",
    methods=["POST"]
)
@role_required("ADMIN")
def approve_withdrawal(
    withdrawal_id
):

    admin = current_user()

    withdrawal = Withdrawal.query.filter_by(
        withdrawal_id=
            withdrawal_id.upper()
    ).first()

    if not withdrawal:

        return jsonify({
            "error":
            "Withdrawal not found"
        }), 404

    if withdrawal.status != "PENDING":

        return jsonify({
            "error":
            "Withdrawal is not pending"
        }), 400

    balance = rewards_for(
        withdrawal.user_id
    )["points"]

    if withdrawal.points > balance:

        withdrawal.status = (
            "REJECTED"
        )

        audit(
            admin.user_id,
            "WITHDRAWAL_REJECTED",
            "WITHDRAWAL",
            withdrawal.withdrawal_id,
            "Insufficient balance"
        )

        db.session.commit()

        return jsonify({
            "error":
            "Insufficient balance; withdrawal rejected"
        }), 400

    withdrawal.status = "APPROVED"

    db.session.add(
        RewardTransaction(

            transaction_id=
                make_id(
                    "RWD",
                    RewardTransaction,
                    "transaction_id"
                ),

            user_id=
                withdrawal.user_id,

            points=
                -withdrawal.points,

            transaction_type=
                "DEBIT",

            reference_id=
                withdrawal.withdrawal_id,

            description=
                (
                    "Approved demo "
                    f"withdrawal ₹"
                    f"{withdrawal.amount}"
                )
        )
    )

    audit(
        admin.user_id,
        "WITHDRAWAL_APPROVED",
        "WITHDRAWAL",
        withdrawal.withdrawal_id,
        f"₹{withdrawal.amount}"
    )

    db.session.commit()

    return jsonify({
        "message":
            "Withdrawal approved",
        "withdrawal_id":
            withdrawal.withdrawal_id
    })


@app.route(
    "/api/admin/withdrawals/<withdrawal_id>/reject",
    methods=["POST"]
)
@role_required("ADMIN")
def reject_withdrawal(
    withdrawal_id
):

    admin = current_user()

    withdrawal = Withdrawal.query.filter_by(
        withdrawal_id=
            withdrawal_id.upper()
    ).first()

    if not withdrawal:

        return jsonify({
            "error":
            "Withdrawal not found"
        }), 404

    if withdrawal.status != "PENDING":

        return jsonify({
            "error":
            "Withdrawal is not pending"
        }), 400

    withdrawal.status = "REJECTED"

    audit(
        admin.user_id,
        "WITHDRAWAL_REJECTED",
        "WITHDRAWAL",
        withdrawal.withdrawal_id,
        "Rejected by supervisor"
    )

    db.session.commit()

    return jsonify({
        "message":
            "Withdrawal rejected"
    })


# ============================================================
# MAIN DASHBOARD
# ============================================================

@app.route("/api/dashboard")
@jwt_required()
def dashboard():

    user = current_user()

    total_users = User.query.count()

    total_handovers = (
        CustomerHandover.query.count()
    )

    total_collections = (
        Collection.query.count()
    )

    verified_collections = (
        Collection.query.filter(
            Collection.status.in_([
                "AGGREGATOR_VERIFIED",
                "RECYCLER_RECEIVED"
            ])
        ).count()
    )

    verified_weight = (
        db.session.query(
            db.func.coalesce(
                db.func.sum(
                    EPRRecord.verified_weight
                ),
                0
            )
        ).scalar()
        or 0
    )

    open_anomalies = (
        AnomalyFlag.query.filter_by(
            resolved=False
        ).count()
    )

    pending_withdrawals = (
        Withdrawal.query.filter_by(
            status="PENDING"
        ).count()
    )

    reward_points = (
        db.session.query(
            db.func.coalesce(
                db.func.sum(
                    RewardTransaction.points
                ),
                0
            )
        ).scalar()
        or 0
    )

    return jsonify({

        "role":
            user.role,

        "user":
            user_json(user),

        "system": {

            "total_users":
                total_users,

            "total_handovers":
                total_handovers,

            "total_collections":
                total_collections,

            "verified_collections":
                verified_collections,

            "verified_weight_kg":
                round(
                    float(
                        verified_weight
                    ),
                    2
                ),

            "open_anomalies":
                open_anomalies,

            "pending_withdrawals":
                pending_withdrawals,

            "reward_points_issued":
                int(
                    reward_points
                )
        },

        "rewards":
            rewards_for(
                user.user_id
            )
    })


# ============================================================
# BRAND / PRO DASHBOARD
# ============================================================

@app.route(
    "/api/brand/dashboard"
)
@role_required(
    "BRAND",
    "ADMIN"
)
def brand_dashboard():

    # Fictional demo obligation.
    # This is NOT a real company integration.

    obligation = 10000.0

    verified = (
        db.session.query(
            db.func.coalesce(
                db.func.sum(
                    EPRRecord.verified_weight
                ),
                0
            )
        ).scalar()
        or 0
    )

    verified = float(
        verified
    )

    remaining = max(
        obligation - verified,
        0
    )

    compliance = (
        (verified / obligation) * 100
        if obligation
        else 0
    )

    eprs = EPRRecord.query.order_by(
        EPRRecord.id.desc()
    ).limit(100).all()

    return jsonify({

        "brand":
            "ECOGEN Electronics",

        "demo":
            True,

        "obligation_kg":
            obligation,

        "verified_epr_kg":
            round(
                verified,
                2
            ),

        "remaining_kg":
            round(
                remaining,
                2
            ),

        "compliance_percent":
            round(
                compliance,
                2
            ),

        "epr_records": [

            {
                "epr_id":
                    epr.epr_id,

                "collection_id":
                    epr.collection_id,

                "weight_kg":
                    epr.verified_weight,

                "status":
                    epr.status,

                "created_at":
                    iso(
                        epr.created_at
                    )
            }

            for epr in eprs
        ]
    })


# ============================================================
# ADMIN - USERS
# ============================================================

@app.route("/api/admin/users")
@role_required("ADMIN")
def admin_users():

    users = User.query.order_by(
        User.id
    ).all()

    return jsonify([
        user_json(user)
        for user in users
    ])


@app.route(
    "/api/admin/users/<user_id>/toggle",
    methods=["POST"]
)
@role_required("ADMIN")
def toggle_user(user_id):

    admin = current_user()

    user = get_user(
        user_id.upper()
    )

    if not user:

        return jsonify({
            "error":
            "User not found"
        }), 404

    if user.user_id == admin.user_id:

        return jsonify({
            "error":
            "Supervisor cannot deactivate self"
        }), 400

    user.active = not user.active

    audit(
        admin.user_id,
        "TOGGLE_USER",
        "USER",
        user.user_id,
        f"active={user.active}"
    )

    db.session.commit()

    return jsonify({

        "message":
            "User status updated",

        "active":
            user.active
    })


# ============================================================
# ADMIN - ANOMALIES
# ============================================================

@app.route("/api/admin/anomalies")
@role_required("ADMIN")
def admin_anomalies():

    anomalies = AnomalyFlag.query.order_by(
        AnomalyFlag.id.desc()
    ).limit(200).all()

    return jsonify([

        {
            "anomaly_id":
                anomaly.anomaly_id,

            "collection_id":
                anomaly.collection_id,

            "reason":
                anomaly.reason,

            "severity":
                anomaly.severity,

            "resolved":
                anomaly.resolved,

            "created_at":
                iso(
                    anomaly.created_at
                )
        }

        for anomaly in anomalies
    ])


@app.route(
    "/api/admin/anomalies/<anomaly_id>/resolve",
    methods=["POST"]
)
@role_required("ADMIN")
def resolve_anomaly(anomaly_id):

    admin = current_user()

    anomaly = AnomalyFlag.query.filter_by(
        anomaly_id=
            anomaly_id.upper()
    ).first()

    if not anomaly:

        return jsonify({
            "error":
            "Anomaly not found"
        }), 404

    anomaly.resolved = True

    audit(
        admin.user_id,
        "RESOLVE_ANOMALY",
        "ANOMALY",
        anomaly.anomaly_id,
        anomaly.reason
    )

    db.session.commit()

    return jsonify({
        "message":
            "Anomaly resolved"
    })


# ============================================================
# ADMIN - AUDIT TRAIL
# ============================================================

@app.route("/api/admin/audit")
@role_required("ADMIN")
def admin_audit():

    logs = AuditLog.query.order_by(
        AuditLog.id.desc()
    ).limit(300).all()

    return jsonify([

        {
            "actor_id":
                log.actor_id,

            "action":
                log.action,

            "entity_type":
                log.entity_type,

            "entity_id":
                log.entity_id,

            "details":
                log.details,

            "created_at":
                iso(
                    log.created_at
                )
        }

        for log in logs
    ])


# ============================================================
# ADMIN - COLLECTION MONITOR
# ============================================================

@app.route("/api/admin/collections")
@role_required("ADMIN")
def admin_collections():

    rows = Collection.query.order_by(
        Collection.id.desc()
    ).limit(300).all()

    return jsonify([
        collection_json(row)
        for row in rows
    ])


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):

    return jsonify({
        "error":
        "Route not found"
    }), 404


@app.errorhandler(500)
def server_error(error):

    db.session.rollback()

    return jsonify({

        "error":
            "Server error",

        "details":
            str(error)
    }), 500


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "5000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )
