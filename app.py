from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime
import hashlib
import uuid


# ============================================================
# APP CONFIGURATION
# ============================================================

app = Flask(__name__, static_folder="frontend")
CORS(app)


# ============================================================
# DEMO DATABASE - IN MEMORY
# ============================================================
# No SQLAlchemy
# Data will reset whenever the server restarts.

collections = {}
handovers = {}
rewards = {}

EPR_OBLIGATION_KG = 10000.0

COLLECTOR_POINTS_PER_KG = 10
CUSTOMER_POINTS_PER_KG = 5


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def generate_id(prefix):
    """Generate a unique transaction ID."""
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def current_time():
    """Return current UTC time as ISO format."""
    return datetime.utcnow().isoformat() + "Z"


def get_json():
    """Safely read JSON request data."""
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {}

    return data


def add_reward(user_id, points):
    """Add reward points to a user."""
    if not user_id:
        return

    if user_id not in rewards:
        rewards[user_id] = 0

    rewards[user_id] += int(points)


def calculate_epr_weight():
    """Calculate total recycler-verified e-waste."""
    total = 0.0

    for item in collections.values():
        if item.get("status") == "EPR_VERIFIED":
            total += float(item.get("recycler_weight", 0))

    return round(total, 2)


# ============================================================
# HOME PAGE
# ============================================================

@app.route("/")
def home():
    """
    Serve index.html from the project root.
    """

    return send_from_directory(".", "index.html")


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "E-Waste EPR Platform"
    })


# ============================================================
# API STATUS
# ============================================================

@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify({
        "status": "online",
        "message": "E-Waste EPR Platform API is running",
        "collections": len(collections),
        "handovers": len(handovers)
    })


# ============================================================
# CUSTOMER HANDOVER
# ============================================================

@app.route("/api/customer/handover", methods=["POST"])
def create_handover():

    data = get_json()

    customer_id = str(data.get("customer_id", "")).strip()
    phone = str(data.get("phone", "")).strip()
    location = str(data.get("location", "")).strip()
    product = str(data.get("product", "")).strip()
    collector_id = str(data.get("collector_id", "")).strip()

    try:
        weight = float(data.get("weight", 0))
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "message": "Weight must be a valid number"
        }), 400

    if not customer_id:
        return jsonify({
            "success": False,
            "message": "Customer ID is required"
        }), 400

    if not product:
        return jsonify({
            "success": False,
            "message": "Product type is required"
        }), 400

    if weight <= 0:
        return jsonify({
            "success": False,
            "message": "Weight must be greater than 0"
        }), 400

    handover_id = generate_id("HO")

    handover = {
        "handover_id": handover_id,
        "customer_id": customer_id,
        "phone": phone,
        "location": location,
        "product": product,
        "weight": weight,
        "collector_id": collector_id,
        "status": "HANDED_OVER",
        "created_at": current_time()
    }

    handovers[handover_id] = handover

    return jsonify({
        "success": True,
        "message": "E-waste handover created",
        "handover": handover
    }), 201


# ============================================================
# GET CUSTOMER HANDOVERS
# ============================================================

@app.route("/api/customer/handovers", methods=["GET"])
def get_handovers():

    return jsonify({
        "success": True,
        "count": len(handovers),
        "handovers": list(handovers.values())
    })


# ============================================================
# COLLECTOR CREATES COLLECTION
# ============================================================

@app.route("/api/collection", methods=["POST"])
def create_collection():

    data = get_json()

    collector_id = str(data.get("collector_id", "")).strip()
    customer_id = str(data.get("customer_id", "")).strip()
    handover_id = str(data.get("handover_id", "")).strip()
    item_type = str(data.get("item_type", "")).strip()
    gps = str(data.get("gps", "")).strip()
    image_hash = str(data.get("image_hash", "")).strip()

    try:
        quantity = int(data.get("quantity", 1))
        weight = float(data.get("weight", 0))
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "message": "Quantity and weight must be valid numbers"
        }), 400

    if not collector_id:
        return jsonify({
            "success": False,
            "message": "Collector ID is required"
        }), 400

    if not item_type:
        return jsonify({
            "success": False,
            "message": "Item type is required"
        }), 400

    if weight <= 0:
        return jsonify({
            "success": False,
            "message": "Weight must be greater than 0"
        }), 400

    if quantity <= 0:
        return jsonify({
            "success": False,
            "message": "Quantity must be greater than 0"
        }), 400

    # If no image hash is supplied, create a transaction hash.
    if not image_hash:
        raw_data = (
            f"{collector_id}|"
            f"{customer_id}|"
            f"{item_type}|"
            f"{weight}|"
            f"{current_time()}"
        )

        image_hash = hashlib.sha256(
            raw_data.encode("utf-8")
        ).hexdigest()

    collection_id = generate_id("EW")

    collection = {
        "collection_id": collection_id,
        "collector_id": collector_id,
        "customer_id": customer_id,
        "handover_id": handover_id,
        "item_type": item_type,
        "quantity": quantity,
        "weight": weight,
        "collector_weight": weight,
        "aggregator_weight": None,
        "recycler_weight": None,
        "gps": gps,
        "image_hash": image_hash,
        "status": "COLLECTED",
        "aggregator_verified": False,
        "recycler_verified": False,
        "epr_verified": False,
        "collector_reward": 0,
        "customer_reward": 0,
        "created_at": current_time()
    }

    collections[collection_id] = collection

    return jsonify({
        "success": True,
        "message": "Collection created successfully",
        "collection": collection
    }), 201


# ============================================================
# GET ALL COLLECTIONS
# ============================================================

@app.route("/api/collections", methods=["GET"])
def get_collections():

    return jsonify({
        "success": True,
        "count": len(collections),
        "collections": list(collections.values())
    })


# ============================================================
# GET SINGLE COLLECTION
# ============================================================

@app.route("/api/collection/<collection_id>", methods=["GET"])
def get_collection(collection_id):

    collection = collections.get(collection_id)

    if not collection:
        return jsonify({
            "success": False,
            "message": "Collection not found"
        }), 404

    return jsonify({
        "success": True,
        "collection": collection
    })


# ============================================================
# AGGREGATOR VERIFICATION
# ============================================================

@app.route("/api/collection/<collection_id>/verify", methods=["POST"])
def verify_collection(collection_id):

    collection = collections.get(collection_id)

    if not collection:
        return jsonify({
            "success": False,
            "message": "Collection not found"
        }), 404

    data = get_json()

    try:
        aggregator_weight = float(
            data.get("aggregator_weight", 0)
        )
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "message": "Invalid aggregator weight"
        }), 400

    if aggregator_weight <= 0:
        return jsonify({
            "success": False,
            "message": "Aggregator weight must be greater than 0"
        }), 400

    collector_weight = float(
        collection.get("collector_weight", 0)
    )

    # Allow maximum 20% difference.
    minimum_weight = collector_weight * 0.80
    maximum_weight = collector_weight * 1.20

    if not (
        minimum_weight
        <= aggregator_weight
        <= maximum_weight
    ):
        return jsonify({
            "success": False,
            "message": (
                "Weight difference is greater than "
                "the allowed 20% tolerance"
            )
        }), 400

    collection["aggregator_weight"] = aggregator_weight
    collection["aggregator_verified"] = True
    collection["status"] = "AGGREGATOR_VERIFIED"
    collection["aggregator_verified_at"] = current_time()

    return jsonify({
        "success": True,
        "message": "Aggregator verification successful",
        "collection": collection
    })


# ============================================================
# RECYCLER RECEIVES E-WASTE
# ============================================================

@app.route("/api/collection/<collection_id>/receive", methods=["POST"])
def recycler_receive(collection_id):

    collection = collections.get(collection_id)

    if not collection:
        return jsonify({
            "success": False,
            "message": "Collection not found"
        }), 404

    # IMPORTANT:
    # Recycler cannot verify a collection
    # until aggregator verification is complete.

    if not collection.get("aggregator_verified"):
        return jsonify({
            "success": False,
            "message": (
                "Aggregator verification is required "
                "before recycler confirmation"
            )
        }), 400

    data = get_json()

    try:
        recycler_weight = float(
            data.get("recycler_weight", 0)
        )
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "message": "Invalid recycler weight"
        }), 400

    if recycler_weight <= 0:
        return jsonify({
            "success": False,
            "message": "Recycler weight must be greater than 0"
        }), 400

    aggregator_weight = float(
        collection.get("aggregator_weight", 0)
    )

    minimum_weight = aggregator_weight * 0.80
    maximum_weight = aggregator_weight * 1.20

    if not (
        minimum_weight
        <= recycler_weight
        <= maximum_weight
    ):
        return jsonify({
            "success": False,
            "message": (
                "Recycler weight differs by more than "
                "20% from aggregator weight"
            )
        }), 400

    # Image hash must exist for final verification.
    if not collection.get("image_hash"):
        return jsonify({
            "success": False,
            "message": "Image verification data is missing"
        }), 400

    collection["recycler_weight"] = recycler_weight
    collection["recycler_verified"] = True
    collection["epr_verified"] = True
    collection["status"] = "EPR_VERIFIED"
    collection["recycler_verified_at"] = current_time()

    # --------------------------------------------------------
    # DEMO REWARD CALCULATION
    # --------------------------------------------------------

    collector_reward = int(
        recycler_weight * COLLECTOR_POINTS_PER_KG
    )

    customer_reward = int(
        recycler_weight * CUSTOMER_POINTS_PER_KG
    )

    collection["collector_reward"] = collector_reward
    collection["customer_reward"] = customer_reward

    add_reward(
        collection.get("collector_id"),
        collector_reward
    )

    add_reward(
        collection.get("customer_id"),
        customer_reward
    )

    # Update customer handover.
    handover_id = collection.get("handover_id")

    if handover_id in handovers:
        handovers[handover_id]["status"] = "EPR_VERIFIED"

    return jsonify({
        "success": True,
        "message": "Recycler receipt confirmed and EPR verified",
        "collection": collection,
        "rewards": {
            "collector_points": collector_reward,
            "customer_points": customer_reward
        }
    })


# ============================================================
# EPR STATUS FOR A COLLECTION
# ============================================================

@app.route("/api/epr/<collection_id>", methods=["GET"])
def get_epr_status(collection_id):

    collection = collections.get(collection_id)

    if not collection:
        return jsonify({
            "success": False,
            "message": "Collection not found"
        }), 404

    verified = collection.get("epr_verified", False)

    return jsonify({
        "success": True,
        "collection_id": collection_id,
        "epr_verified": verified,
        "epr_weight": (
            collection.get("recycler_weight", 0)
            if verified else 0
        ),
        "status": collection.get("status")
    })


# ============================================================
# REWARD BALANCE
# ============================================================

@app.route("/api/rewards/<user_id>", methods=["GET"])
def get_rewards(user_id):

    points = rewards.get(user_id, 0)

    return jsonify({
        "success": True,
        "user_id": user_id,
        "points": points,
        "demo_cash_value": round(points * 0.10, 2)
    })


# ============================================================
# BRAND / PRO DASHBOARD
# ============================================================

@app.route("/api/dashboard", methods=["GET"])
def dashboard():

    verified_weight = calculate_epr_weight()

    remaining = max(
        EPR_OBLIGATION_KG - verified_weight,
        0
    )

    compliance = (
        verified_weight / EPR_OBLIGATION_KG
    ) * 100

    verified_records = [
        item
        for item in collections.values()
        if item.get("status") == "EPR_VERIFIED"
    ]

    return jsonify({
        "success": True,

        "brand": {
            "name": "ECOGEN Electronics",
            "type": "Demo Brand / PRO"
        },

        "epr": {
            "obligation_kg": EPR_OBLIGATION_KG,
            "verified_kg": round(verified_weight, 2),
            "remaining_kg": round(remaining, 2),
            "compliance_percent": round(
                min(compliance, 100),
                2
            )
        },

        "verified_records": len(verified_records),

        "records": verified_records
    })


# ============================================================
# CPCB-READY DEMO REPORT DATA
# ============================================================

@app.route("/api/report", methods=["GET"])
def report():

    verified_weight = calculate_epr_weight()

    return jsonify({
        "report_type": "Demo EPR Compliance Report",
        "brand": "ECOGEN Electronics",
        "epr_obligation_kg": EPR_OBLIGATION_KG,
        "verified_epr_kg": round(verified_weight, 2),
        "remaining_kg": round(
            max(EPR_OBLIGATION_KG - verified_weight, 0),
            2
        ),
        "compliance_percent": round(
            min(
                (verified_weight / EPR_OBLIGATION_KG) * 100,
                100
            ),
            2
        ),
        "verified_records": len([
            x for x in collections.values()
            if x.get("status") == "EPR_VERIFIED"
        ]),
        "generated_at": current_time(),
        "note": (
            "Demo report for prototype presentation. "
            "Not a direct CPCB submission."
        )
    })


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
