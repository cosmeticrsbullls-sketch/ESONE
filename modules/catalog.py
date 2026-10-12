"""Product MRP master transcribed from the supplied October invoice, not sale rates."""
from decimal import Decimal, ROUND_HALF_UP
CATALOG = [
 ('ES-01','ES CLARIFYING SHAMPOO 1LTR',1999),('ES-02','ES KERABEEN 1LTR',7999),
 ('ES-03','ES NANOBEEN 1LTR',16999),('ES-04','ES BEEN BOTOX 1LTR',18999),
 ('ES-05','ES KB SHAMPOO 1LTR',2999),('ES-06','ES NB SHAMPOO 1LTR',3999),
 ('ES-07','ES BB SHAMPOO 1LTR',3999),('ES-08','ES KB SHAMPOO 300ML',999),
 ('ES-09','ES KB CONDITIONER 300ML',999),('ES-10','ES NB SHAMPOO 300ML',1499),
 ('ES-11','ES NB CONDITIONER 300ML',1499),('ES-12','ES BB SHAMPOO 300ML',1499),
 ('ES-13','ES BB CONDITIONER 300ML',1499),('ES-14','ES ARGAN MASK 500GM',1349),
 ('ES-15','ES ARGAN HAIR MASK 250GM',749),('ES-16','ES ARGAN SERUM 50ML',799)]

def price_lines(form):
    lines=[]; subtotal=Decimal(0); total=Decimal(0)
    for sku,name,mrp in CATALOG:
        try:
            qty=int(form.get('qty_'+sku,'0'))
            discount=Decimal(form.get('discount_'+sku,'0'))
            if not 0<=qty<=10000 or not discount.is_finite() or not 0<=discount<=100 or discount!=discount.quantize(Decimal('.01')):raise ValueError()
        except (ValueError,ArithmeticError):raise ValueError('Quantity must be a whole number 0-10000; discount must be 0-100 with at most two decimals.') from None
        if qty:
            gross=Decimal(mrp)*qty; net=(gross*(100-discount)/100).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            lines.append(dict(sku=sku,name=name,mrp=Decimal(mrp),quantity=qty,discount_percent=discount,amount=net))
            subtotal+=gross;total+=net
    if not lines:raise ValueError('Add quantity for at least one product.')
    return lines,subtotal,total
