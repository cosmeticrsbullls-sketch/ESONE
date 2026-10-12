"""Conservative structured extraction for text invoices; never posts ledger data."""
import re
from datetime import datetime
from decimal import Decimal

MONEY=r'\d[\d,]*\.\d{2}'
ITEM=re.compile(r'^\s*(\d+)\s+(.+?)\s+('+MONEY+r')\s+(\d+(?:\.\d+)?)\s+(Pcs|Nos|Unit|Units|Kg|Ltr)\s+('+MONEY+r')\s+('+MONEY+r')\s*$',re.I)

def money(raw):return str(Decimal(raw.replace(',','')).quantize(Decimal('.01')))

def parse_invoice(text):
    lines=[line.strip() for line in text.splitlines() if line.strip()]
    result={'items':[], 'warnings':[]}
    number=re.search(r'(?i)\b(?:invoice|bill)\s*(?:no\.?|number|#)\s*:?\s*(\S+)',text)
    if number:result['reference']=number.group(1)
    for label,key in [('Date','document_date'),('Due Date','due_date')]:
        pattern=re.escape(label).replace(r'\ ',r'\s+')
        candidates=re.finditer(r'(?i)\b'+pattern+r'\s*:\s*(\d{2}-\d{2}-\d{4})',text)
        found=next((match for match in candidates if label!='Date' or not re.search(r'(?:Due|Delivery)\s+$',text[max(0,match.start()-25):match.start()],re.I)),None)
        if found:
            try:result[key]=datetime.strptime(found.group(1),'%d-%m-%Y').date().isoformat()
            except ValueError:result['warnings'].append('Invalid '+label)
    for index,line in enumerate(lines):
        if re.match(r'^bill to(?:\s|$)',line,re.I) and index+1<len(lines):
            side_fields=r'\s+(?:Transport Name|Vehicle Number|Invoice No\.?|Due Date|Delivery Date|Date|Delivery Location)\s*:'
            result['customer_name']=re.split(side_fields,lines[index+1],maxsplit=1,flags=re.I)[0].strip()
            address=[]
            for following in lines[index+2:]:
                if re.match(r'Contact No|Transportation Details|Invoice Details',following,re.I):break
                address.append(re.split(side_fields,following,maxsplit=1,flags=re.I)[0].strip())
            result['customer_address']='\n'.join(address)
        if line.lower()=='payment mode' and index+1<len(lines):result['payment_mode']=lines[index+1]
        match=ITEM.match(line)
        if match:
            seq,name,mrp,qty,unit,rate,amount=match.groups()
            result['items'].append(dict(sequence=int(seq),name=name,mrp=money(mrp),quantity=qty,unit=unit,rate=money(rate),amount=money(amount)))
    contact=re.search(r'(?im)^\s*Contact No\.?\s*:\s*([+\d ()-]+)',text)
    if contact:result['customer_phone']=contact.group(1).strip()
    # Anchored labels separate invoice amounts from cumulative customer balances.
    for label,key in [('Sub Total','subtotal'),('Total','total'),('Received','received'),('Balance','invoice_balance'),('Previous Balance','previous_balance'),('Current Balance','current_balance'),('You Saved','savings')]:
        matches=re.findall(r'(?im)^\s*'+label+r'\s+('+MONEY+r')\s*$',text)
        if matches:result[key]=money(matches[-1])
    result['tax_lines']=[line for line in lines if re.match(r'(?:CGST|SGST|IGST|GST|Tax Amount)\b',line,re.I)]
    items=result['items']
    if items:
        result['total_quantity']=str(sum(Decimal(i['quantity']) for i in items))
        result['items_amount']=str(sum(Decimal(i['amount']) for i in items))
        if result.get('subtotal') and Decimal(result['items_amount'])!=Decimal(result['subtotal']):result['warnings'].append('Line item sum differs from subtotal; check the original.')
        if any(Decimal(i['quantity'])*Decimal(i['rate'])!=Decimal(i['amount']) for i in items):result['warnings'].append('Some quantity × rate values differ from the line amount; review discount/rounding.')
    else:result['warnings'].append('No structured item rows detected. Check the extracted text manually.')
    if all(k in result for k in ['total','received','invoice_balance']) and Decimal(result['total'])-Decimal(result['received'])!=Decimal(result['invoice_balance']):result['warnings'].append('Invoice total minus received differs from bill balance.')
    if all(k in result for k in ['previous_balance','invoice_balance','current_balance']) and Decimal(result['previous_balance'])+Decimal(result['invoice_balance'])!=Decimal(result['current_balance']):result['warnings'].append('Previous balance plus bill balance differs from current balance.')
    return result
