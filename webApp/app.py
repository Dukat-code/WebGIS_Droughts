from flask import Flask, jsonify, render_template
from flask_cors import CORS

##############################################################################

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    a = 3 +2
    return "Hello world! " + str(a)

if __name__ == "__main__":
        app.run(host="0.0.0.0",debug=True)