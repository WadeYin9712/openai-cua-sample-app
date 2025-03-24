from computers import Computer
from computers import LocalPlaywrightComputer
from utils import create_response, check_blocklisted_url


def acknowledge_safety_check_callback(message: str) -> bool:
    response = input(
        f"Safety Check Warning: {message}\nDo you want to acknowledge and proceed? (y/n): "
    ).lower()
    return response.strip() == "y"


def handle_item(item, computer: Computer, call_id: str = None) -> list:
    """Handle each item; may cause a computer action + screenshot."""
    if item["type"] == "message":  # print messages
        print(item["content"][0]["text"])

    if item["type"] == "computer_call":  # perform computer actions
        action = item["action"]
        action_type = action["type"]
        action_args = {k: v for k, v in action.items() if k != "type"}

        # give our computer environment action to perform
        getattr(computer, action_type)(**action_args)

        screenshot_base64 = computer.screenshot()

        pending_checks = item.get("pending_safety_checks", [])
        for check in pending_checks:
            if not acknowledge_safety_check_callback(check["message"]):
                raise ValueError(f"Safety check failed: {check['message']}")

        # return value informs model of the latest screenshot
        call_output = {
            "type": "computer_call_output",
            "call_id": item["call_id"] if call_id is None else call_id,
            "acknowledged_safety_checks": pending_checks,
            "output": {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{screenshot_base64}",
            },
        }

        # additional URL safety checks for browser environments
        if computer.environment == "browser":
            current_url = computer.get_current_url()
            call_output["output"]["current_url"] = current_url
            check_blocklisted_url(current_url)

        return [call_output]

    return []


def main():
    """Run the CUA (Computer Use Assistant) loop, using Local Playwright."""
    with LocalPlaywrightComputer() as computer:
        tools = [
            {
                "type": "computer-preview",
                "display_width": computer.dimensions[0],
                "display_height": computer.dimensions[1],
                "environment": computer.environment,
            }
        ]

        computer.goto("https://copilot.microsoft.com")

        items = []
        while True:  # get user input forever
            user_input = input("> ")
            items.append({"role": "user", "content": user_input})

            turn = 0
            while True:  # keep looping until we get a final response
                response = create_response(
                    model="computer-use-preview",
                    input=items,
                    tools=tools,
                    reasoning={
                        "generate_summary": "concise",
                    },
                    truncation="auto",
                )

                # Introduce the latest arxiv paper in the Computation and Language section
                # You should click Videos in the header

                if "output" not in response:
                    print(response)
                    raise ValueError("No output from model")
            
                items += response["output"]
                print("*******", response["output"])

                if turn <= 1:
                    for item in response["output"]:
                        items += handle_item(item, computer)
                else:
                    critique = input("Critique > ")
                    critique_items = [
                        {
                            "role": "user", 
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": critique
                                },
                                {
                                    "type": "input_image",
                                    "image_url": f"data:image/png;base64,{computer.screenshot()}"
                                }
                            ]
                        }
                    ]

                    while True:       # Once we have a critique, we want to modify the model behavior
                        correction_response = create_response(
                            model="computer-use-preview",
                            input=critique_items,
                            tools=tools,
                            reasoning={
                                "generate_summary": "concise",
                            },
                            truncation="auto",
                        )

                        if "output" not in correction_response:
                            print(correction_response)
                            raise ValueError("No output from model")
                        print(correction_response["output"])

                        critique_items = critique_items + correction_response["output"]
                        
                        if critique_items[-1].get("role") == "assistant":   # Sometimes Operator will have a followup question, then automatically response with "yes"
                            critique_items.append({"role": "user", "content": "Yes!"})
                        else:
                            last_item = correction_response["output"][-1]
                            items[-1]["action"] = last_item["action"]   # replace the last action with the one that should be done according to the critique
                            
                            reverse_index = -1
                            while "call_id" not in items[reverse_index]:
                                reverse_index -= 1

                            if reverse_index < -1:
                                items = items[:reverse_index + 1]
                            items += handle_item(last_item, computer, call_id=items[-1]["call_id"])
                            break

                turn += 1

                if items[-1].get("role") == "assistant":
                    break


if __name__ == "__main__":
    main()
