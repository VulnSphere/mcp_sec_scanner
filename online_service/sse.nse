-- import Nmap libraries
local http = require "http" 
local shortport = require "shortport" 
local stdnse = require "stdnse" 
local string = require "string" 
local table = require "table" 
local nmap = require "nmap" 

-- Script description
description = [[
Checks if a given HTTP path returns a 'Content-Type: text/event-stream' header,
indicating a potential Server-Sent Events (SSE) endpoint.
]]

-- author, license, categories
author = "Centaurisk"
license = "Same as Nmap--See https://nmap.org/book/man-legal.html"

portrule = shortport.port_or_service(
    {80, 443, 8000, 8080},
    {"http", "https", "http-proxy"},
    "tcp"
)

-- Custom HTTP request implementation, using sockets directly
local function send_request(host, port, path)
  -- Create HTTP request
  local request = string.format(
    "GET %s HTTP/1.1\r\n" ..
    "Host: %s:%d\r\n" ..
    "Accept: text/event-stream\r\n" ..
    "Connection: close\r\n\r\n",
    path, host.ip, port.number
  )

  -- Establish connection
  local socket = nmap.new_socket()
  socket:set_timeout(1000) -- 1 second timeout

  local status, err = socket:connect(host, port)
  if not status then
    stdnse.debug1("Socket connection failed: %s", err)
    return nil
  end

  -- Send request
  status, err = socket:send(request)
  if not status then
    stdnse.debug1("Failed to send request: %s", err)
    socket:close()
    return nil
  end

  -- Receive response
  local response = {}
  local total_bytes = 0
  local chunk

  -- Loop to read data until connection is closed
  while true do
    status, chunk = socket:receive()
    if not status then break end

    table.insert(response, chunk)
    total_bytes = total_bytes + #chunk

    -- Add newline, because socket:receive() doesn't preserve these
    if #chunk > 0 then
      table.insert(response, "\r\n")
      total_bytes = total_bytes + 2
    end
  end

  socket:close()

  -- Combine all received data
  local data = table.concat(response)
  stdnse.debug1("Received %d bytes of raw response", total_bytes)

  return data
end

-- Parse HTTP response headers
local function parse_headers(data)
  local headers = {}

  -- Extract status line
  local status_line = string.match(data, "^HTTP/[%d%.]+%s+(%d+)[^\r\n]*\r\n")
  local status = status_line and tonumber(status_line) or 0

  stdnse.debug1("Raw status line: %s", status_line or "nil")
  stdnse.debug1("Parsed status: %d", status)

  -- Extract all headers
  for name, value in string.gmatch(data, "\r\n([^:]+):%s*([^\r\n]*)\r\n") do
    name = string.lower(name)
    headers[name] = value
    stdnse.debug1("Found header: %s = %s", name, value)
  end

  return status, headers
end

-- Extract and parse the response body from a complete HTTP response
local function extract_body(response_data)
  -- Find the separator between headers and body
  local body_start = string.find(response_data, "\r\n\r\n")
  if not body_start then
    stdnse.debug1("Could not find body separator")
    return nil
  end

  -- Extract the body (skip the separator)
  local body = string.sub(response_data, body_start + 4)
  stdnse.debug1("Extracted raw body (%d bytes), first 50 bytes: %s",
                #body, string.sub(body, 1, 50))
  return body
end

-- Parse chunked encoded response and extract SSE events
local function parse_sse_events(body)
  local events = {}

  -- Check for chunked encoding marker, e.g. hexadecimal length value
  local is_chunked = string.match(body, "^%x+\r\n")
  local processed_body = body

  -- Handle chunked encoded response
  if is_chunked then
    stdnse.debug1("Handling chunked encoded response")
    local reconstructed = ""
    local pos = 1

    while pos <= #body do
      -- Find chunk size ending position
      local size_end = string.find(body, "\r\n", pos)
      if not size_end then
        stdnse.debug1("Chunk size ending not found, breaking at position %d", pos)
        break
      end

      -- Parse chunk size
      local size_hex = string.sub(body, pos, size_end - 1)
      local chunk_size = tonumber(size_hex, 16)

      if not chunk_size then
        stdnse.debug1("Invalid chunk size: %s", size_hex)
        break
      end

      stdnse.debug1("Found chunk size: %d bytes", chunk_size)

      if chunk_size == 0 then -- Find last chunk
        stdnse.debug1("End of chunked data (size 0)")
        break
      end

      -- Extract this chunk's content
      local chunk_start = size_end + 2
      local chunk_end = chunk_start + chunk_size - 1

      if chunk_end > #body then
        stdnse.debug1("Warning: Chunk extends beyond body end (%d > %d)", chunk_end, #body)
        chunk_end = #body
      end

      -- Add chunk content to reconstructed body
      local chunk_content = string.sub(body, chunk_start, chunk_end)
      reconstructed = reconstructed .. chunk_content

      -- Print debug information
      stdnse.debug1("Adding chunk content: %s", string.sub(chunk_content, 1, 50))

      -- Move to next block
      pos = chunk_end + 2 -- Skip chunk ending \r\n
    end

    processed_body = reconstructed
    stdnse.debug1("Reconstructed body (%d bytes): %s",
                 #processed_body, string.sub(processed_body, 1, 100))
  end

  -- Parse SSE events
  local current_event = {}

  -- Process SSE data line by line
  for line in string.gmatch(processed_body, "([^\r\n]+)") do
    stdnse.debug2("Processing line: %s", line)

    -- Skip comment lines
    if string.sub(line, 1, 1) == ":" then
      -- Comment line, ignore
    -- Check event field
    elseif string.find(line, "^event:") then
      current_event.type = string.match(line, "^event:%s*(.*)")
      stdnse.debug1("Found event type: %s", current_event.type)
    -- Check data field
    elseif string.find(line, "^data:") then
      current_event.data = string.match(line, "^data:%s*(.*)")
      stdnse.debug1("Found event data: %s", current_event.data)
    -- Empty line indicates event end
    elseif line == "" then
      -- If we have a complete event, add it to the results
      if current_event.type and current_event.data then
        table.insert(events, {
          type = current_event.type,
          data = current_event.data
        })
        stdnse.debug1("Added complete event: type=%s, data=%s",
                     current_event.type, current_event.data)
      end
      -- Reset current event
      current_event = {}
    end
  end

  -- Process final event (if no empty line ends the event)
  if current_event.type and current_event.data then
    table.insert(events, {
      type = current_event.type,
      data = current_event.data
    })
    stdnse.debug1("Added final event: type=%s, data=%s",
                 current_event.type, current_event.data)
  end

  return events
end

-- Main execution logic
action = function(host, port)
  -- Get script arguments
  local path = stdnse.get_script_args("sse.path") or "/sse"
  local output = {}

  stdnse.debug1("Checking %s:%d for SSE endpoint at path: %s", host.ip, port.number, path)

  -- Send request and get response
  local response_data = send_request(host, port, path)

  if not response_data then
    stdnse.debug1("No response data received")
    return nil
  end

  -- Parse HTTP status and headers
  local status, headers = parse_headers(response_data)
  if not headers then
    stdnse.debug1("Failed to parse HTTP headers")
    return nil
  end

  -- Check content type is SSE
  local content_type = headers["content-type"]
  stdnse.debug1("Content type: %s", content_type or "nil")

  local is_sse = false
  if content_type then
    local lowercase_content_type = string.lower(content_type)
    is_sse = string.find(lowercase_content_type, "text/event-stream", 1, true) ~= nil
    stdnse.debug1("Content type matches SSE: %s", is_sse and "yes" or "no")
  end

  -- Check status code and content type
  if status >= 200 and status < 300 and is_sse then
    -- Found SSE endpoint
    local result = string.format("SSE endpoint found at %s (Content-Type: %s)", path, content_type)
    table.insert(output, result)
    stdnse.debug1(result)

    -- Extract response body
    local body = extract_body(response_data)
    if not body then
      stdnse.debug1("Could not extract response body")
      table.insert(output, "  -> SSE endpoint detected but couldn't extract body")
      return stdnse.format_output(true, output)
    end

    -- Parse SSE events
    local events = parse_sse_events(body)

    -- Output discovered events
    if #events > 0 then
      table.insert(output, string.format("  -> Found %d SSE event(s):", #events))
      for i, event in ipairs(events) do
        table.insert(output, string.format("    Event: %s, Data: %s", event.type, event.data))
      end
    else
      table.insert(output, "  -> SSE connection established but no events parsed")
    end

    -- Return formatted result
    return stdnse.format_output(true, output)
  else
    if not is_sse then
      stdnse.debug1("Not an SSE endpoint (Content-Type is not text/event-stream): %s", content_type or "nil")
    else
      stdnse.debug1("Non-success status code: %d", status)
    end
  end

  -- If no SSE endpoint found, return nil
  return nil
end