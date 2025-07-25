import json
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import logging
import socket
import os

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 存储转发规则的文件
RULES_FILE = 'proxy_rules.json'

# 存储转发规则：{本地端口: {目标IP, 目标端口, 备注}}
proxy_rules = {}

# 管理页面文件路径
ADMIN_PAGE_FILE = 'admin_page.html'

def load_rules():
    """从文件加载转发规则"""
    global proxy_rules
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, 'r', encoding='utf-8') as f:
                proxy_rules = json.load(f)
            logger.info(f"已加载 {len(proxy_rules)} 条转发规则")
        except Exception as e:
            logger.error(f"加载规则文件失败: {e}")
            proxy_rules = {}
    else:
        logger.info("规则文件不存在，将使用空规则")
        proxy_rules = {}

def save_rules():
    """保存转发规则到文件"""
    try:
        with open(RULES_FILE, 'w') as f:
            json.dump(proxy_rules, f)
        logger.info(f"已保存 {len(proxy_rules)} 条转发规则")
    except Exception as e:
        logger.error(f"保存规则文件失败: {e}")

def get_server_ip():
    """获取服务器IP地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def get_free_port():
    """获取一个空闲端口"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    return port

def load_admin_page():
    """加载管理页面内容"""
    try:
        with open(ADMIN_PAGE_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"加载管理页面失败: {e}")
        return f"<h1>Error loading admin page</h1><p>{str(e)}</p>"

class AdminRequestHandler(BaseHTTPRequestHandler):
    """HTTP管理接口请求处理类"""
    def _send_response(self, content, status=200, content_type='text/html'):
        self.send_response(status)
        self.send_header('Content-type', content_type)
        self.end_headers()
        self.wfile.write(content.encode('utf-8'))
    
    def do_GET(self):
        """处理GET请求"""
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/':
            # 返回管理页面
            admin_page = load_admin_page()
            # 替换服务器IP地址
            admin_page = admin_page.replace('{server_ip}', get_server_ip())
            self._send_response(admin_page)
        elif parsed_path.path == '/api/rules':
            # 返回当前规则列表
            self._send_response(json.dumps(proxy_rules), content_type='application/json')
        else:
            self._send_response('404 Not Found', 404)
    
    def do_POST(self):
        """处理POST请求"""
        parsed_path = urlparse(self.path)
        if parsed_path.path == '/api/add_rule':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            data = parse_qs(post_data)
            try:
                local_port = data.get('local_port', [''])[0]
                remote_ip = data.get('remote_ip', [''])[0]
                remote_port = data.get('remote_port', [''])[0]
                remark = data.get('remark', [''])[0]
                # 如果本地端口为空，则自动分配一个空闲端口
                if not local_port:
                    local_port = str(get_free_port())
                if not remote_ip or not remote_port:
                    self._send_response(json.dumps({'success': False, 'message': '目标IP和端口不能为空'}), content_type='application/json')
                    return
                if local_port in proxy_rules:
                    self._send_response(json.dumps({'success': False, 'message': f'端口 {local_port} 已被使用'}), content_type='application/json')
                    return
                # 规则结构支持备注
                proxy_rules[local_port] = {
                    'remote_ip': remote_ip,
                    'remote_port': remote_port,
                    'remark': remark
                }
                save_rules()
                self._send_response(json.dumps({'success': True, 'message': f'已添加转发规则: {local_port} -> {remote_ip}:{remote_port}', 'local_port': local_port}), content_type='application/json')
            except Exception as e:
                self._send_response(json.dumps({'success': False, 'message': f'添加规则失败: {str(e)}'}), content_type='application/json')
            return
        elif parsed_path.path == '/api/remove_rule':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            data = parse_qs(post_data)
            local_port = data.get('local_port', [''])[0]
            if not local_port or local_port not in proxy_rules:
                self._send_response(json.dumps({'success': False, 'message': '未找到该端口的规则'}), content_type='application/json')
                return
            del proxy_rules[local_port]
            save_rules()
            self._send_response(json.dumps({'success': True}), content_type='application/json')
            return
        else:
            self._send_response('404 Not Found', 404)

def start_admin_server(port=8080):
    """启动管理服务器"""
    server_address = ('0.0.0.0', port)
    httpd = ThreadingHTTPServer(server_address, AdminRequestHandler)
    logger.info(f"管理服务器已启动，访问 http://{get_server_ip()}:{port} 进行管理")
    httpd.serve_forever()

if __name__ == "__main__":
    # 加载转发规则
    load_rules()
    
    # 检查管理页面文件是否存在
    if not os.path.exists(ADMIN_PAGE_FILE):
        logger.error(f"管理页面文件 {ADMIN_PAGE_FILE} 不存在！")
        exit(1)
    
    # 启动管理服务器
    try:
        start_admin_server()
    except KeyboardInterrupt:
        logger.info("管理服务器已关闭")

