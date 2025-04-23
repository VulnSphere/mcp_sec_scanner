For the security detection of MCP ecosystem software(WIP)

1. online_service

The main purpose is to detect and analyze the SSE format of the MCP Service

Firstly, use masscan to scan the target IP range's port and then analyze the returned results to detect whether there is an event: endpoint.

Or use nmap's script to directly detect the 'Content-Type: text/event-stream'.

Then use sse_tool.py to perform the actual test.

2. source_code

The main purpose is to collect and analyze the source code of the MCP server

Firstly, collect the server list from the mcpso/github,
Then clone/pull all the source code

Finally, use LLM to analyze the source code
    - Unexpected behavior detection
    - Security vulnerability detection

3. Middleware

4. MCP Client
