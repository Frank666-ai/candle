#!/bin/bash

# 启动后端
echo "Starting Backend..."
cd backend
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt
nohup uvicorn main:app --reload --host 0.0.0.0 --port 8000 > ../backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend started with PID $BACKEND_PID"

# 启动前端
echo "Starting Frontend..."
cd ../frontend
# 确保依赖已安装
if [ ! -d "node_modules" ]; then
    npm install
fi
nohup npm run dev -- --host > ../frontend.log 2>&1 &
FRONTEND_PID=$!
echo "Frontend started with PID $FRONTEND_PID"

echo "Services are running!"
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo "Logs are being written to backend.log and frontend.log"

# 等待用户按键退出
read -p "Press any key to stop services..."

kill $BACKEND_PID
kill $FRONTEND_PID
echo "Services stopped."

