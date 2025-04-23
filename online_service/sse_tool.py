#!/usr/bin/env python3
import sys
import argparse
import asyncio
import logging
import random
import json

from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

async def try_resource_operations(session: ClientSession):
    print("\n== list_resources ==")
    try:
        resources = await session.list_resources()
        print(resources.model_dump_json(by_alias=True, exclude_none=True, indent=2))
        
        for resource in resources.resources:
            uri = resource.uri
            print(f"\n== read_resource {uri} ==")
            try:
                resource_content = await session.read_resource(uri)
                print(resource_content.model_dump_json(by_alias=True, exclude_none=True, indent=2))
            except Exception as e:
                print(f"read resource failed: {e}")
                
            print(f"\n== subscribe_resource {uri} ==")
            try:
                await session.subscribe_resource(uri)
                print("subscribe resource success")
                await asyncio.sleep(1) 
                
                print(f"\n== unsubscribe_resource {uri} ==")
                await session.unsubscribe_resource(uri)
                print("unsubscribe resource success")
            except Exception as e:
                print(f"subscribe resource failed: {e}")
    except Exception as e:
        print(f"list resources failed: {e}")
        
    print("\n== list_resource_templates ==")
    try:
        templates = await session.list_resource_templates()
        print(templates.model_dump_json(by_alias=True, exclude_none=True, indent=2))
    except Exception as e:
        print(f"list resource templates failed: {e}")

async def try_prompt_operations(session: ClientSession):
    print("\n== prompt operations ==")

    print("\n== list_prompts ==")
    try:
        prompts = await session.list_prompts()
        print(prompts.model_dump_json(by_alias=True, exclude_none=True, indent=2))
        
        for prompt in prompts.prompts:
            prompt_name = prompt.name
            print(f"\n== get_prompt {prompt_name} ==")
            try:
                prompt = await session.get_prompt(prompt_name)
                print(prompt.model_dump_json(by_alias=True, exclude_none=True, indent=2))
            except Exception as e:
                print(f"get prompt failed: {e}")
    except Exception as e:
        print(f"list prompts failed: {e}")

async def generate_test_parameters(tool_schema):
    """Generate test parameters based on inputSchema"""
    if not tool_schema or not isinstance(tool_schema, dict):
        return {}
        
    test_params = {}
    properties = tool_schema.get("properties", {})
    required = tool_schema.get("required", [])
    
    for param_name, param_spec in properties.items():
        # If it's a required parameter or we want to fully test, generate a value
        if param_name in required or True:
            param_type = param_spec.get("type")
            
            # For complex types containing anyOf, try to find the main type
            if "anyOf" in param_spec:
                for type_option in param_spec["anyOf"]:
                    if type_option.get("type") and type_option.get("type") != "null":
                        param_type = type_option.get("type")
                        break
            
            # Generate appropriate test value based on parameter type and name
            if param_type == "string":
                test_params[param_name] = "admin"
                # test_params[param_name] = "\"'><script>alert('XSS')</script>"
            elif param_type == "integer":
                # Use default value or set a reasonable integer
                default = param_spec.get("default")
                test_params[param_name] = default if default is not None else -1
            elif param_type == "number":
                # Use default value or set a reasonable number
                default = param_spec.get("default")
                test_params[param_name] = default if default is not None else -1.0
            elif param_type == "array":
                # Generate simple test data for array type
                if random.random() > 0.85:
                    test_params[param_name] = [-1, 2**32] 
                else:
                    test_params[param_name] = ["'", ">"]
            elif param_type == "object":
                # Recursively generate test data for object type
                sub_properties = param_spec.get("properties", {})
                test_params[param_name] = {k: "test_value" for k in sub_properties.keys()}
    
    return test_params

async def try_tool_operations(session: ClientSession):
    """tool operations"""
    print("\n== tool operations ==")
    
    # list tools
    print("\n== list_tools ==")
    try:
        tools = await session.list_tools()
        print(tools.model_dump_json(by_alias=True, exclude_none=True, indent=2))
        
        # test all available tools
        for tool in tools.tools:
            tool_name = tool.name
            print(f"\n== call_tool {tool_name} ==")
            try:
                # generate test parameters based on tool input schema
                input_schema = tool.inputSchema
                test_params = await generate_test_parameters(input_schema)
                
                # show the parameters we will use
                print(f"using parameters: {test_params}")
                
                # call tool
                result = await session.call_tool(tool_name, test_params)
                print(result.model_dump_json(by_alias=True, exclude_none=True, indent=2))
            except Exception as e:
                print(f"call tool failed: {e}")
    except Exception as e:
        print(f"list tools failed: {e}")

async def main():
    parser = argparse.ArgumentParser(description="MCP SSE test tool")
    parser.add_argument("--url", required=True,
                        help="SSE endpoint URL, e.g. http://IP:8000/sse")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="show verbose logs")
    parser.add_argument("--tool", "-t", type=str,
                        help="tool name to test")
    args = parser.parse_args()

    # set log level
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level)
    
    # set httpx log level to warning to avoid too many request outputs
    if not args.verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)

    print(f"connecting to {args.url}...")
    try:
        async with sse_client(args.url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                print("\n== initialize ==")
                init_res = await session.initialize()
                print(init_res.model_dump_json(by_alias=True, exclude_none=True, indent=2))
                print(f"\nserver info: {init_res.serverInfo.name} v{init_res.serverInfo.version}")
                
                # # test ping
                # print("\n== ping ==")
                # ping_res = await session.send_ping()
                # print(ping_res.model_dump_json(by_alias=True, exclude_none=True, indent=2))
                
                # if specified tool, only execute the specified tool
                if args.tool:
                    # list tools and get input schema
                    tools = await session.list_tools()
                    schema = None
                    for t in tools.tools:
                        if t.name == args.tool:
                            schema = t.inputSchema
                            break
                    if not schema:
                        print(f"tool {args.tool} not found")
                        return
                    # show parameter names and types
                    props = schema.get("properties", {})
                    print("tool parameters:")
                    for name, spec in props.items():
                        print(f"- {name}: {spec.get('type')}")
                    # interactive get parameters and type conversion
                    params = {}
                    for name, spec in props.items():
                        ptype = spec.get('type')
                        raw = input(f"Enter parameter '{name}' (type: {ptype}): ")
                        try:
                            if ptype == 'integer':
                                params[name] = int(raw)
                            elif ptype == 'number':
                                params[name] = float(raw)
                            elif ptype == 'array':
                                params[name] = [json.loads(v) if v.strip().startswith(('"','{','[')) else v.strip() for v in raw.split(',')]
                            elif ptype == 'object':
                                params[name] = json.loads(raw)
                            elif ptype == 'boolean':
                                params[name] = json.loads(raw)
                            else:
                                params[name] = raw
                        except Exception:
                            params[name] = raw
                    # call tool
                    print(f"testing parameters: {params}")
                    result = await session.call_tool(args.tool, params)
                    print(result.model_dump_json(by_alias=True, exclude_none=True, indent=2))
                    return
                    
                # default test resources, prompts and all tools
                await try_resource_operations(session)
                await try_prompt_operations(session)
                await try_tool_operations(session)
                
                # test set logging level
                print("\n== set_logging_level ==")
                try:
                    await session.set_logging_level("info")
                    print("set logging level success")
                except Exception as e:
                    print(f"set logging level failed: {e}")
                
                # test send progress notification
                print("\n== send_progress_notification ==")
                try:
                    await session.send_progress_notification("test_token", 0.5, 1.0)
                    print("send progress notification success")
                except Exception as e:
                    print(f"send progress notification failed: {e}")
                
    except Exception as e:
        print(f"connection or session error: {e}")
        import traceback
        traceback.print_exc()
        return 1
        
    print("\n== test completed ==")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
