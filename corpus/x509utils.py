import ipaddress, datetime

################################################################################

def parse_zulu_time(s):
	"""Parses a zulutime text string (i.e. yyyymmddThhmmssZ) into a datetime object."""

	return datetime.datetime(int(s[0:4]), int(s[4:6]), int(s[6:8]), int(s[8:10]), int(s[10:12]), int(s[12:14]))

################################################################################

def read_asn1_string(byte_string, offset):
	"""Reads an ASN1 IA5 String (i.e. a string where all octets are < 128)."""

	# Get the length of the string
	(length, offset) = read_asn1_length(byte_string, offset)

	if length != -1:
		return (byte_string[offset:offset + length], offset + length)
	else:
		# Search for the end of the string
		end_byte_idx = offset
		while byte_string[end_byte_offset] != 0b10000000:
			end_byte_idx = end_byte_idx + 1

		return (byte_string[offset:end_byte_index], end_byte_index + 1)

################################################################################

def read_asn1_length(byte_string, offset):
	"""Reads an ASN1 length."""

	# ASN1 lengths can be determined by single byte, multibyte, or be unknown
	length_data = ord(byte_string[offset])
	length_lead = (length_data & 0b10000000) >> 7
	length_tail = length_data & 0b01111111
	if length_lead == 0:
		# Single byte, contained, short length ( < 128 bytes )
		length = length_tail
		offset = offset + 1
	elif length_lead == 1 and length_tail == 0:
		# Indefinite (unknown) length
		length = -1
		offset = offset + 1
	elif length_lead == 1 and length_tail == 127:
		raise ValueError('Reserved length in ASN1 length octet')
	else:
		length_bytes = length_tail
		length_byte_idx = offset + 1
		offset = offset + 1
		length_end_byte = length_byte_idx + length_bytes
		length = 0
		while length_byte_idx < length_end_byte:
			length = length << 8
			length = length | ord(byte_string[length_byte_idx])
			length_byte_idx = length_byte_idx + 1
			offset = offset + 1

	return (length, offset)

################################################################################

def decode_subject_alt_name(byte_string):
	"""Decodes a subjectAltName value into something usable."""

	results = []

	# A quick summary of ASN1 tags:
	# Format: Single octet bits: AABCCCCC
	#    AA = Tag Class (00 = Universal, 01 = Application, 02 = Context-specific, 03 = Private)
	#     B = Primitive (0) or Constructed (1)
	# CCCCC = Tag number (see the ASN1 docs)
	context_type = ord(byte_string[0])
	if context_type == 0b00110000:	# Universal, Constructed, Sequence
		# Length follows the ASN1 tag
		(length, first_data_byte_idx) = read_asn1_length(byte_string, 1)

		# We've established our sequence length and where the first byte is.
		# Now it gets complicated
		byte_idx = first_data_byte_idx
		while byte_idx < length + 2:
			seq_el_type = ord(byte_string[byte_idx])
			byte_idx = byte_idx + 1
			
			if   seq_el_type == 0b10000000:  # otherName [0]
				raise ValueError('Unsupported subjectAltName type (0)')
			elif seq_el_type == 0b10000001:  # rfc822Name [1]
				(result, byte_idx) = read_asn1_string(byte_string, byte_idx)
				results.append((1, result))
			elif seq_el_type == 0b10000010:  # dNSName [2]
				(result, byte_idx) = read_asn1_string(byte_string, byte_idx)
				results.append((2, result))
			elif seq_el_type == 0b10000011:  # x400Address [3]
				raise ValueError('Unsupported subjectAltName type (3)')
			elif seq_el_type == 0b10000100:  # directoryName [4]
				raise ValueError('Unsupported subjectAltName type (4)')
			elif seq_el_type == 0b10000101:  # ediPartyName [5]
				raise ValueError('Unsupported subjectAltName type (5)')
			elif seq_el_type == 0b10000110:  # uniformResourceIdentifier [6]
				(result, byte_idx) = read_asn1_string(byte_string, byte_idx)
				results.append((6, result))
			elif seq_el_type == 0b10000111:  # IPAddress [7]
				(result, byte_idx) = read_asn1_string(byte_string, byte_idx)
				if len(result) == 4:
					result = ipaddress.IPv4Address(result).exploded
				elif len(result) == 16:
					result = ipaddress.IPv6Address(result).exploded
				else:
					raise ValueError('Invalid IP address data in subjectAltName')
				results.append((7, result))
			elif seq_el_type == 0b10001000:  # registeredID [8]
				raise ValueError('Unsupported subjectAltName type (8)')
			else:
				raise ValueError('Unknown subjectAltName type (' + str(seq_el_type) + ')')

		return results

	else:
		raise ValueError('subjectAltName does not start with ASN1 sequence')

################################################################################

def get_subject_alt_names(cert):
	"""Takes a OpenSSL.crypto.X509 object and extracts a list of SANs."""

	sans = []
	for i in range(0, cert.get_extension_count()):
		ext = cert.get_extension(i)
		if ext.get_short_name() == 'subjectAltName':
			alt_names = decode_subject_alt_name(ext.get_data())
			for name in alt_names:
				if   name[0] == 1:  # 
					sans.append('RFC822:' + name[1])
				elif name[0] == 2:  # DNS name
					sans.append('DNS:' + name[1])
				elif name[0] == 6:  # URI
					sans.append('URI:' + name[1])
				elif name[0] == 7:
					sans.append('IPAddress:' + str(name[1]))

	return sans
