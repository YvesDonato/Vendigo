"""Authoritative Vendigo procedure supplied by the application owner.

This describes the intended paid lifecycle. It configures no hardware and does not
turn the demo storefront into a payment-verifying backend.
"""

LID_OPEN_SECONDS = 7


def vendi_knowledge():
    return {
        "robot_name": "Vendi",
        "company": "Vendigo",
        "purchase_process": {
            "scan_qr": "opens the Vendigo mobile web app only",
            "select_product": "choose from current inventory and pay through the web app",
            "server_verified_payment_required": True,
            "qr_scan_authorizes_dispensing": False,
            "success_page_authorizes_dispensing": False,
            "dispense_authority": "verified server-side payment/order event only",
            "controller_path": "application/Raspberry Pi instructs ESP32; never the conversational model",
            "after_verification": "announce payment received, then open the compartment",
            "lid_open_seconds": LID_OPEN_SECONDS,
            "lid_auto_closes": True,
            "after_collection": "close automatically, say goodbye/complete transaction, return to roaming/vendor mode",
        },
    }
