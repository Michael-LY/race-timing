"""赛道计时应用 - 开发服务器入口"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    # 开发服务器：监听 0.0.0.0:5000，开启调试模式
    app.run(debug=True, host="0.0.0.0", port=5000)
