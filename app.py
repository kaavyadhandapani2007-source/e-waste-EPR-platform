from flask import Flask, jsonify, request, send_from_directory
from datetime import datetime
import hashlib
import os

app = Flask(__name__)

# ============================================================
# TEMPORARY DATABASE
# ============================================================
# For the hackathon demo, data is stored in memory.
# Later this can be replaced with PostgreSQL.

collections = {}


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():
    return send_from_directory(
        os.path.dirname(os.path.abspath(__file__)),
        "index.html"
    )


# ============================================================
# SYSTEM STATUS
# ============================================================

@app.route("/api/status", methods=["GET"])
def status():

    return jsonify({
        "server": "online",
        "database": "temporary memory database",
        "total_collections": len(collections),
        "system": "E-Waste EPR Platform",
        "version": "1.0"
    })


# ============================================================
# CREATE COLLECTION
# ============================================================

@app.route("/api/collection", methods=["POST"])
def create_collection():

    data = request.get_json()

    if not data:
        return jsonify({
            "success": False,
            "message": "No JSON data received"
        }), 400

    collector_id = data.get("collector_id")
    item_type = data.get("item_type")
    quantity = data.get("quantity")
    weight = data.get("weight")

    # -----------------------------
    # VALIDATION
    # -----------------------------

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

    if quantity is None:
        return jsonify({
            "success": False,
            "message": "Quantity is required"
        }), 400

    if weight is None:
        return jsonify({
            "success": False,
            "message": "Weight is required"
        }), 400

    try:
        quantity = int(quantity)
        weight = float(weight)
    except (ValueError, TypeError):

        return jsonify({
            "success": False,
            "message": "Quantity and weight must be valid numbers"
        }), 400

    if quantity <= 0 or weight <= 0:

        return jsonify({
            "success": False,
            "message": "Quantity and weight must be greater than zero"
        }), 400

    # ========================================================
    # UNIQUE COLLECTION ID
    # ========================================================

    collection_id = (
        "EW-" +
        datetime.now().strftime("%Y%m%d%H%M%S%f")
    )

    timestamp = datetime.now().isoformat()

    # ========================================================
    # IMAGE HASH
    # ========================================================

    image_hash = data.get("image_hash")

    if not image_hash:

        image_hash = hashlib.sha256(
            collection_id.encode()
        ).hexdigest()

    # ========================================================
    # COLLECTION RECORD
    # ========================================================

    collection = {

        "collection_id": collection_id,

        "collector_id": collector_id,

        "item_type": item_type,

        "quantity": quantity,

        "collector_weight": weight,

        "aggregator_weight": None,

        "recycler_weight": None,

        "photo": data.get("photo"),

        "image_hash": image_hash,

        "latitude": data.get("latitude"),

        "longitude": data.get("longitude"),

        "timestamp": timestamp,

        "status": "SUBMITTED",

        "aggregator_verified": False,

        "recycler_confirmed": False,

        "epr_verified": False,

        "reward_points": 0
    }

    collections[collection_id] = collection

    return jsonify({

        "success": True,

        "message": "Collection recorded successfully!",

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

@app.route(
    "/api/collection/<collection_id>/verify",
    methods=["POST"]
)
def aggregator_verify(collection_id):

    collection = collections.get(collection_id)

    if not collection:

        return jsonify({

            "success": False,

            "message": "Collection not found"

        }), 404

    data = request.get_json() or {}

    aggregator_weight = data.get("weight")

    if aggregator_weight is None:

        return jsonify({

            "success": False,

            "message": "Aggregator weight is required"

        }), 400

    try:

        aggregator_weight = float(aggregator_weight)

    except (ValueError, TypeError):

        return jsonify({

            "success": False,

            "message": "Invalid aggregator weight"

        }), 400

    if aggregator_weight <= 0:

        return jsonify({

            "success": False,

            "message": "Aggregator weight must be greater than zero"

        }), 400

    # ========================================================
    # SAVE VERIFICATION
    # ========================================================

    collection["aggregator_weight"] = aggregator_weight

    collection["aggregator_verified"] = True

    collection["status"] = "AGGREGATOR_VERIFIED"

    return jsonify({

        "success": True,

        "message": "Aggregator verification completed!",

        "collection": collection

    })


# ============================================================
# RECYCLER RECEIPT
# ============================================================

@app.route(
    "/api/collection/<collection_id>/receive",
    methods=["POST"]
)
def recycler_receive(collection_id):

    collection = collections.get(collection_id)

    if not collection:

        return jsonify({

            "success": False,

            "message": "Collection not found"

        }), 404

    # ========================================================
    # AGGREGATOR MUST VERIFY FIRST
    # ========================================================

    if not collection["aggregator_verified"]:

        return jsonify({

            "success": False,

            "message": "Aggregator verification is required first"

        }), 400

    data = request.get_json() or {}

    recycler_weight = data.get("weight")

    if recycler_weight is None:

        return jsonify({

            "success": False,

            "message": "Recycler weight is required"

        }), 400

    try:

        recycler_weight = float(recycler_weight)

    except (ValueError, TypeError):

        return jsonify({

            "success": False,

            "message": "Invalid recycler weight"

        }), 400

    if recycler_weight <= 0:

        return jsonify({

            "success": False,

            "message": "Recycler weight must be greater than zero"

        }), 400

    # ========================================================
    # SAVE RECEIPT
    # ========================================================

    collection["recycler_weight"] = recycler_weight

    collection["recycler_confirmed"] = True

    collection["status"] = "RECYCLER_CONFIRMED"

    # ========================================================
    # TRUST VERIFICATION
    # ========================================================

    verification = verify_collection_record(collection)

    if verification["valid"]:

        collection["status"] = "EPR_VERIFIED"

        collection["epr_verified"] = True

        # Demo reward:
        # 10 points per verified kg

        collection["reward_points"] = int(
            recycler_weight * 10
        )

    else:

        collection["status"] = "FLAGGED"

        collection["epr_verified"] = False

        collection["reward_points"] = 0

    return jsonify({

        "success": True,

        "message": "Recycler receipt processed!",

        "verification": verification,

        "collection": collection

    })


# ============================================================
# TRUST / FRAUD VERIFICATION
# ============================================================

def verify_collection_record(collection):

    checks = {}

    # --------------------------------------------------------
    # CHECK 1: Aggregator verification
    # --------------------------------------------------------

    checks["aggregator_verified"] = (
        collection["aggregator_verified"]
    )

    # --------------------------------------------------------
    # CHECK 2: Recycler confirmation
    # --------------------------------------------------------

    checks["recycler_confirmed"] = (
        collection["recycler_confirmed"]
    )

    # --------------------------------------------------------
    # CHECK 3: Weight consistency
    # --------------------------------------------------------

    collector_weight = collection["collector_weight"]

    aggregator_weight = collection["aggregator_weight"]

    recycler_weight = collection["recycler_weight"]

    weight_valid = True

    # Collector → Aggregator

    if aggregator_weight is not None:

        difference = abs(
            collector_weight -
            aggregator_weight
        )

        if difference > collector_weight * 0.20:

            weight_valid = False

    # Aggregator → Recycler

    if (
        recycler_weight is not None
        and aggregator_weight is not None
    ):

        difference = abs(
            aggregator_weight -
            recycler_weight
        )

        if difference > aggregator_weight * 0.20:

            weight_valid = False

    checks["weight_consistency"] = weight_valid

    # --------------------------------------------------------
    # CHECK 4: Image hash
    # --------------------------------------------------------

    checks["image_hash"] = bool(
        collection.get("image_hash")
    )

    # --------------------------------------------------------
    # FINAL DECISION
    # --------------------------------------------------------

    valid = all(checks.values())

    if valid:

        message = (
            "Collection passed trust verification."
        )

    else:

        message = (
            "Collection requires further verification."
        )

    return {

        "valid": valid,

        "checks": checks,

        "message": message

    }


# ============================================================
# EPR RECORD
# ============================================================

@app.route(
    "/api/epr/<collection_id>",
    methods=["GET"]
)
def get_epr_record(collection_id):

    collection = collections.get(collection_id)

    if not collection:

        return jsonify({

            "success": False,

            "message": "Collection not found"

        }), 404

    if not collection["epr_verified"]:

        return jsonify({

            "success": False,

            "message": "EPR record not generated yet",

            "status": collection["status"]

        }), 400

    epr_record = {

        "epr_record_id":
            "EPR-" + collection_id,

        "collection_id":
            collection["collection_id"],

        "collector_id":
            collection["collector_id"],

        "item_type":
            collection["item_type"],

        "verified_weight":
            collection["recycler_weight"],

        "channel":
            "Informal Collector → Aggregator → Recycler",

        "verification_status":
            "VERIFIED",

        "epr_credit":
            collection["recycler_weight"],

        "generated_at":
            datetime.now().isoformat()

    }

    return jsonify({

        "success": True,

        "epr_record": epr_record

    })


# ============================================================
# BRAND / PRO DASHBOARD
# ============================================================

@app.route("/api/dashboard", methods=["GET"])
def dashboard():

    total_collections = len(collections)

    total_weight = 0

    verified_weight = 0

    pending = 0

    flagged = 0

    reward_points = 0

    # ========================================================
    # CALCULATE PLATFORM METRICS
    # ========================================================

    for collection in collections.values():

        total_weight += float(
            collection.get(
                "collector_weight",
                0
            )
        )

        reward_points += int(
            collection.get(
                "reward_points",
                0
            )
        )

        if collection["epr_verified"]:

            verified_weight += float(
                collection.get(
                    "recycler_weight",
                    0
                )
            )

        elif collection["status"] == "FLAGGED":

            flagged += 1

        else:

            pending += 1

    # ========================================================
    # DEMO EPR OBLIGATION
    # ========================================================

    epr_obligation = 10000

    remaining = max(
        epr_obligation -
        verified_weight,
        0
    )

    compliance = 0

    if epr_obligation > 0:

        compliance = (
            verified_weight /
            epr_obligation
        ) * 100

    return jsonify({

        "success": True,

        "dashboard": {

            "total_collections":
                total_collections,

            "total_collector_weight":
                round(
                    total_weight,
                    2
                ),

            "verified_epr_weight":
                round(
                    verified_weight,
                    2
                ),

            "pending_collections":
                pending,

            "flagged_collections":
                flagged,

            "reward_points":
                reward_points,

            "epr_obligation":
                epr_obligation,

            "epr_remaining":
                round(
                    remaining,
                    2
                ),

            "compliance_percentage":
                round(
                    compliance,
                    2
                )
        }

    })


# ============================================================
# COLLECTOR REWARDS
# ============================================================

@app.route(
    "/api/rewards/<collector_id>",
    methods=["GET"]
)
def collector_rewards(collector_id):

    total_points = 0

    verified_collections = 0

    for collection in collections.values():

        if (
            collection["collector_id"]
            == collector_id
        ):

            total_points += int(
                collection.get(
                    "reward_points",
                    0
                )
            )

            if collection["epr_verified"]:

                verified_collections += 1

    return jsonify({

        "success": True,

        "collector_id":
            collector_id,

        "verified_collections":
            verified_collections,

        "reward_points":
            total_points,

        "redemption":
            "UPI redemption can be integrated later."

    })


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health", methods=["GET"])
def health():

    return jsonify({

        "status": "healthy",

        "service":
            "E-Waste EPR Platform",

        "timestamp":
            datetime.now().isoformat()

    })


# ============================================================
# RUN SERVER LOCALLY
# ============================================================
# Render uses Gunicorn, so this section is only for local use.

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
