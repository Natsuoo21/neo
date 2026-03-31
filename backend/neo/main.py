"""Neo CLI — Interactive command interface."""


def main():
    """Start the Neo interactive CLI."""
    print("Neo — Personal Intelligence Agent")
    print("Type a command or 'quit' to exit.\n")

    while True:
        try:
            command = input("Neo> ").strip()
            if not command:
                continue
            if command.lower() in ("quit", "exit", "q"):
                print("Goodbye.")
                break
            # TODO: Route to orchestrator.process(command)
            print(f"[stub] Received: {command}")
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            break


if __name__ == "__main__":
    main()
