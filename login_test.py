from SmartApi import SmartConnect
import pyotp

API_KEY = "JRyUUxSU"
CLIENT_ID = "K339542"
PIN = "0586"
TOTP_SECRET = "LRWKXRNC7RVJI7TV7QJV753FBM"


def login():
    try:
        smart = SmartConnect(api_key=API_KEY)

        # Generate TOTP
        totp = pyotp.TOTP(TOTP_SECRET).now()

        # Create Session (NO PASSWORD REQUIRED)
        data = smart.generateSession(CLIENT_ID, PIN, totp)

        print("==== LOGIN SUCCESS ====")
        print("JWT Token:", data["data"]["jwtToken"])

        return smart

    except Exception as e:
        print("LOGIN FAILED:", e)


if __name__ == "__main__":
    login()