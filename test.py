from app.messages import make_message, parse_message, MessageType

msg = make_message(MessageType.ELECTION, 2, {"candidate_id": 5})
print(msg)

parsed = parse_message(msg)
print(parsed)
