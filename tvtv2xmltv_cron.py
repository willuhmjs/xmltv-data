#!/usr/bin/env python3

import sys
import requests
import math
from datetime import datetime, timedelta
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError # Requires Python 3.9+

# --- Configuration ---
TIMEZONE = "America/New_York"  # Set to your local timezone
LINEUP_ID = "USA-OTA23456"     # Set this to ID of the Line Up data
DAYS = 8                       # Number of days to collect (8 max)
OUTPUT_FILE = "/data/guide.xml" 
# ---------------------

def get_json_data(url):
    """Fetches JSON data from a URL with error handling."""
    try:
        response = requests.get(url, headers={'User-Agent': 'tvtv2xmltv-cron/1.0'})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from {url}: {e}", file=sys.stderr)
        return None
    except requests.exceptions.JSONDecodeError as e:
        print(f"Error decoding JSON from {url}: {e}", file=sys.stderr)
        return None

def main():
    """Main function to generate the XMLTV guide."""
    
    try:
        local_tz = ZoneInfo(TIMEZONE)
    except ZoneInfoNotFoundError:
        print(f"Error: Timezone '{TIMEZONE}' not found.", file=sys.stderr)
        sys.exit(1)

    # --- We will write the output to a list of strings first ---
    output_lines = []

    # --- Build XMLTV data ---
    source_url = "https://www.tvtv.us" 
    now_utc = datetime.now(ZoneInfo("UTC"))
    start_time_str = now_utc.strftime('%Y-%m-%dT00:00:00.000Z')

    output_lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    output_lines.append(f'<tv date="{start_time_str}" source-info-url="{source_url}" source-info-name="tvtv2xmltv">')

    # --- GET lineup data ---
    lineup_url = f"https://www.tvtv.us/api/v1/lineup/{LINEUP_ID}/channels"
    print(f"Fetching lineup from: {lineup_url}", file=sys.stderr)
    lineup_data = get_json_data(lineup_url)

    if not lineup_data:
        output_lines.append("</tv>")
        print("Failed to fetch lineup data. Exiting.", file=sys.stderr)
        # Still write the partial file so the server has *something*
        try:
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                f.write("\n".join(output_lines))
        except IOError as e:
            print(f"Error writing partial file: {e}", file=sys.stderr)
        sys.exit(1)

    all_channels = []
    for channel in lineup_data:
        all_channels.append(channel.get("stationId"))

        channel_num = escape(channel.get("channelNumber", ""))
        call_sign = escape(channel.get("stationCallSign", ""))
        logo_url = escape(channel.get("logo", ""))
        
        output_lines.append(f'  <channel id="{channel_num}">')
        output_lines.append(f'    <display-name>{channel_num}</display-name>')
        output_lines.append(f'    <display-name>{call_sign}</display-name>')
        if logo_url:
            output_lines.append(f'    <icon src="https://www.tvtv.us{logo_url}" />')
        output_lines.append(f'  </channel>')

    # --- Get max 8 days of guide data ---
    max_days = min(DAYS, 8)
    
    for day_offset in range(max_days):
        start_dt = datetime.now() + timedelta(days=day_offset)
        end_dt = datetime.now() + timedelta(days=day_offset + 1)
        
        start_time_api = start_dt.strftime('%Y-%m-%dT04:00:00.000Z')
        end_time_api = end_dt.strftime('%Y-%m-%dT03:59:00.000Z')

        print(f"Fetching guide data for day {day_offset + 1}/{max_days}...", file=sys.stderr)

        listing_data = []
        channel_count = len(all_channels)
        for i in range(0, channel_count, 20):
            channels_batch = all_channels[i:i+20]
            channels_str = ",".join(map(str, channels_batch))
            listing_url = f"https://www.tvtv.us/api/v1/lineup/{LINEUP_ID}/grid/{start_time_api}/{end_time_api}/{channels_str}"
            
            print(f"  Fetching batch {math.ceil((i+1)/20)}/{math.ceil(channel_count/20)}", file=sys.stderr)
            batch_data = get_json_data(listing_url)
            if batch_data:
                listing_data.extend(batch_data)

        # --- Program Data ---
        for index, channel in enumerate(lineup_data):
            if index >= len(listing_data):
                break
                
            for program in listing_data[index]:
                try:
                    title = escape(program.get('title', ''))
                    subtitle = escape(program.get('subtitle', ''))
                    program_type = escape(program.get('type', ''))
                    flags = ", ".join(program.get('flags', []))

                    t_start_utc = datetime.fromisoformat(program['startTime'].replace('Z', '+00:00'))
                    t_start_local = t_start_utc.astimezone(local_tz)
                    
                    run_time = int(program.get('runTime', 0))
                    t_end_local = t_start_local + timedelta(minutes=run_time)
                    
                    start_time_xml = t_start_local.strftime('%Y%m%d%H%M%S %z')
                    end_time_xml = t_end_local.strftime('%Y%m%d%H%M%S %z')

                    output_lines.append(f'    <programme start="{start_time_xml}" stop="{end_time_xml}" channel="{channel.get("channelNumber", "")}">')
                    output_lines.append(f'      <title lang="en">{title}</title>')
                    if subtitle:
                        output_lines.append(f'      <sub-title lang="en">{subtitle}</sub-title>')
                    if program_type == "M":
                        output_lines.append('      <category lang="en">movie</category>')
                    if program_type == "N":
                        output_lines.append('      <category lang="en">news</category>')
                    if program_type == "S":
                        output_lines.append('      <category lang="en">sports</category>')
                    if "EI" in flags:
                        output_lines.append('      <category lang="en">kids</category>')
                    if "HD" in flags:
                        output_lines.append('      <video><quality>HDTV</quality></video>')
                    if "Stereo" in flags:
                        output_lines.append('      <audio><stereo>stereo</stereo></audio>')
                    if "New" in flags:
                        output_lines.append('      <new />')
                    output_lines.append('    </programme>')
                
                except (ValueError, TypeError, KeyError) as e:
                    print(f"Error processing program data: {e}. Program: {program}", file=sys.stderr)
                    continue

    output_lines.append("</tv>")
    
    # --- Write the final file ---
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write("\n".join(output_lines))
        print(f"Successfully wrote guide to {OUTPUT_FILE}", file=sys.stderr)
    except IOError as e:
        print(f"Error writing to output file {OUTPUT_FILE}: {e}", file=sys.stderr)
        sys.exit(1)
        
    print("Done.", file=sys.stderr)

if __name__ == "__main__":
    main()