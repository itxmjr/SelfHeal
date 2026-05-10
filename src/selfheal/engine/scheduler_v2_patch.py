import datetime as dt

def _build_continuous_blocks(hours, today):
    blocks = []
    if not hours: return blocks
    current_start = None
    current_end = None
    current_status = None
    
    for h in sorted(hours, key=lambda x: x["hour"]):
        if h["status"] in ("committed",):
            continue
            
        slot_start = dt.datetime.combine(today, dt.time(h["hour"], 0))
        slot_end = slot_start + dt.timedelta(hours=1)
        
        if current_status == h["status"] and current_end == slot_start:
            current_end = slot_end
        else:
            if current_start is not None:
                blocks.append({"start": current_start, "end": current_end, "status": current_status})
            current_start = slot_start
            current_end = slot_end
            current_status = h["status"]
            
    if current_start is not None:
         blocks.append({"start": current_start, "end": current_end, "status": current_status})
    return blocks

def _allocate_task(blocks, needed_minutes, preferred_statuses):
    for status in preferred_statuses:
        for i, block in enumerate(blocks):
            if block["status"] == status:
                block_mins = int((block["end"] - block["start"]).total_seconds() / 60)
                if block_mins >= needed_minutes:
                    allocated_start = block["start"]
                    allocated_end = allocated_start + dt.timedelta(minutes=needed_minutes)
                    
                    block["start"] = allocated_end
                    if block["start"] >= block["end"]:
                        blocks.pop(i)
                    return allocated_start, allocated_end
    
    # Fallback to any block that fits
    for i, block in enumerate(blocks):
        block_mins = int((block["end"] - block["start"]).total_seconds() / 60)
        if block_mins >= needed_minutes:
            allocated_start = block["start"]
            allocated_end = allocated_start + dt.timedelta(minutes=needed_minutes)
            
            block["start"] = allocated_end
            if block["start"] >= block["end"]:
                blocks.pop(i)
            return allocated_start, allocated_end
            
    return None, None
