from flask import Flask, jsonify, request, send_from_directory
from datetime import datetime
import hashlib
import os

app = Flask(__name__)


# ============================================================
# TEMPORARY DATABASE
# ============================================================
# For now, data is stored in memory.
# Later we will replace this with PostgreSQL.

collections = {}


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():
    return send_from_directory(".","index.html")

# ============================================================
# SYSTEM STATUS
# ============================================================

@app.route("/api/status", methods=["GET"])
def status():

    return jsonify({
        "server": "online",
        "database": "temporary memory database",
        "total_collections": len(collections),
        "system": "E-Waste EPR Platform"
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

    # Required fields
    collector_id = data.get("collector_id")
    item_type = data.get("item_type")
    quantity = data.get("quantity")
    weight = data.get("weight")

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

    # Generate collection ID
    collection_id = "EW-" + datetime.now().strftime("%Y%m%d%H%M%S")

    # Timestamp
    timestamp = datetime.now().isoformat()

    # Create image hash if image_hash supplied
    image_hash = data.get("image_hash")

    if not image_hash:
        image_hash = hashlib.sha256(
            collection_id.encode()
        ).hexdigest()

    # Collection record
    collection = {

        "collection_id": collection_id,

        "collector_id": collector_id,

        "item_type": item_type,

        "quantity": quantity,

        "collector_weight": float(weight),

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

    # Save record
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
# GET ONE COLLECTION
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

    aggregator_weight = float(aggregator_weight)

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

@app.route("/api/collection/<collection_id>/receive", methods=["POST"])
def recycler_receive(collection_id):

    collection = collections.get(collection_id)

    if not collection:

        return jsonify({
            "success": False,
            "message": "Collection not found"
        }), 404

    data = request.get_json() or {}

    recycler_weight = data.get("weight")

    if recycler_weight is None:

        return jsonify({
            "success": False,
            "message": "Recycler weight is required"
        }), 400

    recycler_weight = float(recycler_weight)

    collection["recycler_weight"] = recycler_weight

    collection["recycler_confirmed"] = True

    collection["status"] = "RECYCLER_CONFIRMED"

    # Run verification
    verification = verify_collection_record(collection)

    if verification["valid"]:

        collection["status"] = "EPR_VERIFIED"

        collection["epr_verified"] = True

        # Reward points
        collection["reward_points"] = int(
            recycler_weight * 10
        )

    else:

        collection["status"] = "FLAGGED"

    return jsonify({
        "success": True,
        "message": "Recycler receipt processed!",
        "verification": verification,
        "collection": collection
    })


# ============================================================
# VERIFICATION / TRUST ENGINE
# ============================================================

def verify_collection_record(collection):

    checks = {}

    # --------------------------------------------------------
    # CHECK 1 — Aggregator verification
    # --------------------------------------------------------

    checks["aggregator_verified"] = (
        collection["aggregator_verified"]
    )


    # --------------------------------------------------------
    # CHECK 2 — Recycler confirmation
    # --------------------------------------------------------

    checks["recycler_confirmed"] = (
        collection["recycler_confirmed"]
    )


    # --------------------------------------------------------
    # CHECK 3 — Weight consistency
    # --------------------------------------------------------

    collector_weight = collection["collector_weight"]

    aggregator_weight = collection["aggregator_weight"]

    recycler_weight = collection["recycler_weight"]

    weight_valid = True

    if aggregator_weight is not None:

        difference = abs(
            collector_weight - aggregator_weight
        )

        # Allow 20% difference for demo
        if difference > collector_weight * 0.20:

            weight_valid = False

    if recycler_weight is not None:

        difference = abs(
            aggregator_weight - recycler_weight
        )

        # Allow 20% difference for demo
        if difference > aggregator_weight * 0.20:

            weight_valid = False

    checks["weight_consistency"] = weight_valid


    # --------------------------------------------------------
    # CHECK 4 — Image hash
    # --------------------------------------------------------

    checks["image_hash"] = bool(
        collection.get("image_hash")
    )


    # --------------------------------------------------------
    # FINAL VERIFICATION
    # --------------------------------------------------------

    valid = all(checks.values())

    if valid:

        message = "Collection passed trust verification."

    else:

        message = "Collection requires further verification."


    return {

        "valid": valid,

        "checks": checks,

        "message": message
    }


# ============================================================
# EPR RECORD
# ============================================================

@app.route("/api/epr/<collection_id>", methods=["GET"])
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
# DASHBOARD
# ============================================================

@app.route("/api/dashboard", methods=["GET"])
def dashboard():

    total_collections = len(collections)

    total_weight = 0

    verified_weight = 0

    pending = 0

    flagged = 0

    reward_points = 0


    for collection in collections.values():

        total_weight += collection["collector_weight"]

        reward_points += collection["reward_points"]

        if collection["epr_verified"]:

            verified_weight += (
                collection["recycler_weight"]
            )

        elif collection["status"] == "FLAGGED":

            flagged += 1

        else:

            pending += 1


    # Demo EPR obligation
    epr_obligation = 10000

    remaining = max(
        epr_obligation - verified_weight,
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
                round(total_weight, 2),

            "verified_epr_weight":
                round(verified_weight, 2),

            "pending_collections":
                pending,

            "flagged_collections":
                flagged,

            "reward_points":
                reward_points,

            "epr_obligation":
                epr_obligation,

            "epr_remaining":
                round(remaining, 2),

            "compliance_percentage":
                round(compliance, 2)
        }
    })


# ============================================================
# COLLECTOR REWARDS
# ============================================================

@app.route("/api/rewards/<collector_id>", methods=["GET"])
def collector_rewards(collector_id):

    total_points = 0

    verified_collections = 0


    for collection in collections.values():

        if (
            collection["collector_id"]
            == collector_id
        ):

            total_points += (
                collection["reward_points"]
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
# RUN SERVER
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
        debug=True
    )
