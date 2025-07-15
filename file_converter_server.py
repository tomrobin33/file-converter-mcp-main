from mcp.server.fastmcp import FastMCP, Context
import os
import base64
from pathlib import Path
import tempfile
import mimetypes
import json
import glob
import logging
import sys
import time
import traceback
from sse_starlette.sse import EventSourceResponse  # 添加SSE支持
from fastapi import Request  # 添加FastAPI请求支持

# ... [保持原有的日志配置和辅助函数不变] ...

# 修改FastMCP初始化，允许SSE
mcp = FastMCP("File Converter", enable_sse=True)

# 修改debug_json_response函数以支持SSE
def debug_json_response(response, ctx: Context = None):
    """
    Debug JSON response and send via SSE if context provided.
    """
    try:
        json_str = json.dumps(response, cls=SafeJSONEncoder)
        json.loads(json_str)  # Validate JSON
        
        # 如果有SSE上下文，通过SSE发送
        if ctx and hasattr(ctx, 'sse'):
            ctx.sse.send(json_str)
            return None  # 对于SSE连接，不需要返回HTTP响应
        
        return response  # 对于普通HTTP连接，返回响应
    except Exception as e:
        logger.error(f"Invalid JSON response: {str(e)}")
        error_response = {"success": False, "error": "Internal server error: Invalid JSON response"}
        
        if ctx and hasattr(ctx, 'sse'):
            ctx.sse.send(json.dumps(error_response))
            return None
        
        return error_response

# 修改所有工具函数，添加ctx参数并通过SSE发送进度更新
@mcp.tool("docx2pdf")
def convert_docx_to_pdf(input_file: str = None, file_content_base64: str = None, ctx: Context = None) -> dict:
    try:
        if ctx and hasattr(ctx, 'sse'):
            ctx.sse.send(json.dumps({"status": "start", "message": "Starting DOCX to PDF conversion"}))
        
        # ... [保持原有的转换逻辑不变] ...
        
        # 添加进度更新
        if ctx and hasattr(ctx, 'sse'):
            ctx.sse.send(json.dumps({"status": "progress", "message": "Converting document..."}))
        
        # ... [保持原有的转换逻辑] ...
        
        # 在关键步骤添加进度更新
        if ctx and hasattr(ctx, 'sse'):
            ctx.sse.send(json.dumps({"status": "progress", "message": "Encoding PDF file..."}))
        
        # ... [保持原有的逻辑] ...
        
        # 最终响应将通过debug_json_response发送
        return debug_json_response(format_success_response(encoded_data), ctx)
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return debug_json_response(format_error_response(f"Error converting DOCX to PDF: {str(e)}"), ctx)

# 为所有其他工具函数添加类似的修改（pdf2docx, convert_image等）
# ... [为每个工具函数添加ctx参数和进度更新] ...

# 添加SSE路由处理
@mcp.app.get("/sse")
async def sse_endpoint(request: Request):
    """
    SSE endpoint for streaming conversion progress.
    """
    async def event_generator():
        try:
            # 这里只是示例，实际实现需要与工具集成
            yield {"event": "message", "data": "SSE connection established"}
            
            # 在实际使用中，工具函数会通过ctx.sse发送事件
            # 这只是一个保持连接活跃的示例
            while True:
                if await request.is_disconnected():
                    logger.info("SSE connection disconnected")
                    break
                await asyncio.sleep(5)
                yield {"event": "heartbeat", "data": "ping"}
        except asyncio.CancelledError:
            logger.info("SSE connection cancelled")
    
    return EventSourceResponse(event_generator())

# 修改Context类以支持SSE
class Context:
    def __init__(self, sse=None, **kwargs):
        self.sse = sse  # SSE事件发射器
        # ... [其他属性] ...
    
    def send_progress(self, message):
        """发送进度更新"""
        if self.sse:
            self.sse.send(json.dumps({"status": "progress", "message": message}))

# 修改工具调用处理以支持SSE
def handle_tool_execution(tool_func, params, sse=None):
    """
    Execute tool function with SSE context
    """
    ctx = Context(sse=sse)
    
    # 发送开始事件
    if sse:
        sse.send(json.dumps({"status": "start", "tool": tool_func.__name__}))
    
    try:
        result = tool_func(**params, ctx=ctx)
        
        # 对于SSE连接，工具函数不返回HTTP响应
        # 而是通过SSE发送最终结果
        if sse:
            if result is None:
                # 工具函数已经通过SSE发送了响应
                return None
            else:
                # 如果工具函数返回了结果但没有发送SSE，我们在这里发送
                sse.send(json.dumps(result))
                return None
        
        return result
    except Exception as e:
        logger.error(f"Tool execution error: {str(e)}")
        if sse:
            sse.send(json.dumps({"status": "error", "error": str(e)}))
            return None
        return format_error_response(str(e))

# 修改主运行函数以支持SSE
if __name__ == "__main__":
    import uvicorn
    from mcp.server import fastmcp
    
    # 覆盖工具执行处理
    fastmcp.handle_tool_execution = handle_tool_execution
    
    # 运行服务器
    uvicorn.run(
        mcp.app, 
        host="0.0.0.0", 
        port=8000,
        # 为SSE配置超时
        timeout_keep_alive=60 * 60  # 1小时保持连接
    )
