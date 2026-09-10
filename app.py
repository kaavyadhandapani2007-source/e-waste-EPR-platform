from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from datetime import datetime
import hashlib
import os

app = Flask(__name__)
CORS(app)

# ============================================================
# DEMO DATABASE
# ============================================================

collections = {}
customers = {}
rewards = {}

# Demo EPR obligation for Brand / PRO
EPR_OBLIGATION_KG = 10000

# Demo reward rates
COLLECTOR_POINTS_PER_KG = 10
CUSTOMER_POINTS_PER_KG = 5


# ============================================================
# FRONTEND
# ============================================================

@app.route("/")
def home():
    return send_from_directory(
        os.path.dirname(os.path.abspath(__file__)),
        "index.html"
    )


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "service": "E-Waste EPR Platform"
    })


@app.route("/api/status")
def status():
    return jsonify({
        "status": "online",
        "platform": "E-Waste EPR Platform",
        "version": "2.0"
    })


# ============================================================
# CUSTOMER
# ============================================================

@app.route("/api/customer/handover", methods=["POST"])
def create_handover():

    data = request.get_json() or {}

    customer_id = data.get("customer_id")
    phone = data.get("phone")
    location = data.get("location")
    product = data.get("product")
    weight = data.get("weight")
    collector_id = data.get("collector_id")

    if not customer_id:
        return jsonify({"error": "Customer ID is required"}), 400

    if not phone:
        return jsonify({"error": "Customer phone number is required"}), 400

    if not location:
        return jsonify({"error": "Location is required"}), 400

    if not product:
        return jsonify({"error": "Product type is required"}), 400

    if not weight:
        return jsonify({"error": "Weight is required"}), 400

    try:
        weight = float(weight)
    except ValueError:
        return jsonify({"error": "Invalid weight"}), 400

    handover_id = (
        "HO-" +
        datetime.now().strftime("%Y%m%d%H%M%S%f")
    )

    record = {
        "handover_id": handover_id,
        "customer_id": customer_id,
        "phone": phone,
        "location": location,
        "product": product,
        "weight": weight,
        "collector_id": collector_id,
        "status": "PENDING_PICKUP",
        "risk_status": "LOW_RISK",
        "created_at": datetime.now().isoformat()
    }

    customers[handover_id] = record

    return jsonify({
        "message": "Handover request created",
        "handover": record
    }), 201


@app.route("/api/customer/handovers")
def get_handovers():

    return jsonify({
        "count": len(customers),
        "handovers": list(customers.values())
    })


# ============================================================
# COLLECTION
# ============================================================

@app.route("/api/collection", methods=["POST"])
def create_collection():

    data = request.get_json() or {}

    collector_id = data.get("collector_id")
    item_type = data.get("item_type")
    quantity = data.get("quantity")
    weight = data.get("weight")
    gps = data.get("gps")
    image_hash = data.get("image_hash")
    customer_id = data.get("customer_id")
    handover_id = data.get("handover_id")

    if not collector_id:
        return jsonify({"error": "Collector ID is required"}), 400

    if not item_type:
        return jsonify({"error": "Item type is required"}), 400

    if not weight:
        return jsonify({"error": "Weight is required"}), 400

    try:
        weight = float(weight)
    except ValueError:
        return jsonify({"error": "Invalid weight"}), 400

    collection_id = (
        "EW-" +
        datetime.now().strftime("%Y%m%d%H%M%S%f")
    )

    # If frontend does not provide hash,
    # create a demo hash from transaction data.
    if not image_hash:
        hash_source = (
            f"{collector_id}"
            f"{item_type}"
            f"{weight}"
            f"{datetime.now().isoformat()}"
        )

        image_hash = hashlib.sha256(
            hash_source.encode()
        ).hexdigest()

    record = {
        "collection_id": collection_id,
        "collector_id": collector_id,
        "customer_id": customer_id,
        "handover_id": handover_id,
        "item_type": item_type,
        "quantity": quantity,
        "collector_weight": weight,
        "aggregator_weight": None,
        "recycler_weight": None,
        "gps": gps,
        "image_hash": image_hash,
        "aggregator_verified": False,
        "recycler_received": False,
        "epr_status": "PENDING",
        "collector_reward": 0,
        "customer_reward": 0,
        "created_at": datetime.now().isoformat()
    }

    collections[collection_id] = record

    # Link customer handover to collection
    if handover_id in customers:
        customers[handover_id]["status"] = "COLLECTED"

    return jsonify({
        "message": "Collection created",
        "collection": record
    }), 201


@app.route("/api/collections")
def get_collections():

    return jsonify({
        "count": len(collections),
        "collections": list(collections.values())
    })


@app.route("/api/collection/<collection_id>")
def get_collection(collection_id):

    record = collections.get(collection_id)

    if not record:
        return jsonify({
            "error": "Collection not found"
        }), 404

    return jsonify(record)


# ============================================================
# AGGREGATOR VERIFICATION
# ============================================================

@app.route("/api/collection/<collection_id>/verify", methods=["POST"])
def verify_collection(collection_id):

    record = collections.get(collection_id)

    if not record:
        return jsonify({
            "error": "Collection not found"
        }), 404

    data = request.get_json() or {}

    aggregator_weight = data.get("aggregator_weight")

    if aggregator_weight is None:
        return jsonify({
            "error": "Aggregator weight is required"
        }), 400

    try:
        aggregator_weight = float(aggregator_weight)
    except ValueError:
        return jsonify({
            "error": "Invalid aggregator weight"
        }), 400

    original_weight = float(record["collector_weight"])

    # Allow 20% tolerance
    lower = original_weight * 0.80
    upper = original_weight * 1.20

    if not (lower <= aggregator_weight <= upper):

        record["aggregator_weight"] = aggregator_weight
        record["aggregator_verified"] = False

        return jsonify({
            "message": "Weight mismatch. Manual review required.",
            "status": "REVIEW_REQUIRED"
        }), 400

    record["aggregator_weight"] = aggregator_weight
    record["aggregator_verified"] = True

    return jsonify({
        "message": "Aggregator verification successful",
        "collection": record
    })


# ============================================================
# RECYCLER RECEIPT
# ============================================================

@app.route("/api/collection/<collection_id>/receive", methods=["POST"])
def recycler_receive(collection_id):

    record = collections.get(collection_id)

    if not record:
        return jsonify({
            "error": "Collection not found"
        }), 404

    # Recycler cannot confirm before aggregator
    if not record["aggregator_verified"]:
        return jsonify({
            "error": "Aggregator verification required first"
        }), 400

    data = request.get_json() or {}

    recycler_weight = data.get("recycler_weight")

    if recycler_weight is None:
        return jsonify({
            "error": "Recycler weight is required"
        }), 400

    try:
        recycler_weight = float(recycler_weight)
    except ValueError:
        return jsonify({
            "error": "Invalid recycler weight"
        }), 400

    aggregator_weight = float(
        record["aggregator_weight"]
    )

    lower = aggregator_weight * 0.80
    upper = aggregator_weight * 1.20

    if not (lower <= recycler_weight <= upper):

        return jsonify({
            "error": "Recycler weight does not match verified weight",
            "status": "REVIEW_REQUIRED"
        }), 400

    if not record.get("image_hash"):

        return jsonify({
            "error": "Image verification required"
        }), 400

    record["recycler_weight"] = recycler_weight
    record["recycler_received"] = True
    record["epr_status"] = "EPR_VERIFIED"

    # ========================================================
    # REWARD CALCULATION
    # ========================================================

    collector_points = int(
        recycler_weight * COLLECTOR_POINTS_PER_KG
    )

    customer_points = int(
        recycler_weight * CUSTOMER_POINTS_PER_KG
    )

    record["collector_reward"] = collector_points
    record["customer_reward"] = customer_points

    collector_id = record["collector_id"]
    customer_id = record.get("customer_id")

    # Collector wallet
    rewards.setdefault(collector_id, 0)
    rewards[collector_id] += collector_points

    # Customer wallet
    if customer_id:
        rewards.setdefault(customer_id, 0)
        rewards[customer_id] += customer_points

    # Update customer handover
    handover_id = record.get("handover_id")

    if handover_id in customers:

        customers[handover_id]["status"] = "VERIFIED"

        customers[handover_id][
            "reward_points"
        ] = customer_points

    return jsonify({
        "message": "Recycler confirmation successful",
        "collection": record,
        "rewards": {
            "collector_points": collector_points,
            "customer_points": customer_points
        }
    })


# ============================================================
# EPR RECORD
# ============================================================

@app.route("/api/epr/<collection_id>")
def get_epr(collection_id):

    record = collections.get(collection_id)

    if not record:
        return jsonify({
            "error": "EPR record not found"
        }), 404

    if record["epr_status"] != "EPR_VERIFIED":
        return jsonify({
            "error": "EPR is not verified yet"
        }), 400

    return jsonify({
        "epr_id": "EPR-" + collection_id,
        "collection_id": collection_id,
        "verified_weight": record["recycler_weight"],
        "status": "VERIFIED",
        "collector_id": record["collector_id"],
        "customer_id": record.get("customer_id")
    })


# ============================================================
# REWARDS
# ============================================================

@app.route("/api/rewards/<user_id>")
def get_rewards(user_id):

    return jsonify({
        "user_id": user_id,
        "points": rewards.get(user_id, 0),
        "demo_cash_value": rewards.get(user_id, 0) * 0.10
    })


# ============================================================
# BRAND / PRO DASHBOARD
# ============================================================

@app.route("/api/dashboard")
def dashboard():

    verified_records = [
        c for c in collections.values()
        if c["epr_status"] == "EPR_VERIFIED"
    ]

    verified_weight = sum(
        float(c["recycler_weight"])
        for c in verified_records
    )

    remaining = max(
        EPR_OBLIGATION_KG - verified_weight,
        0
    )

    compliance = (
        verified_weight / EPR_OBLIGATION_KG
    ) * 100 if EPR_OBLIGATION_KG else 0

    return jsonify({

        "brand": "ECOGEN Electronics",

        "epr_obligation_kg": EPR_OBLIGATION_KG,

        "verified_epr_kg": round(
            verified_weight, 2
        ),

        "remaining_kg": round(
            remaining, 2
        ),

        "compliance_percentage": round(
            compliance, 2
        ),

        "verified_records": verified_records
    })


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
