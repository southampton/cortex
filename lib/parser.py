from pyparsing import (
	CaselessKeyword, Forward, Literal, Optional, QuotedString, Word, ZeroOrMore, alphanums, alphas, nums)

# pylint: disable=invalid-name

## Helper classes for parsed tokens ############################################

class VariableComparison:
	"""Stores the details about a single query within a larger search
	expression. Contains the variable name, operator and comparison value."""

	def __init__(self, left, operator, right):
		self.left = left
		self.operator = operator
		self.right = right

	def __str__(self):
		return str((self.left, self.operator, self.right))

class BooleanOperator:
	"""Stores the name of a boolean operator."""

	def __init__(self, operator):
		self.operator = operator

	def __str__(self):
		return "BooleanOperator(" + self.operator + ")"

class StartSubExpression:
	"""Type for starting a subexpression."""

	def __str__(self):
		return "("

class EndSubExpression:
	"""Type for starting a subexpression."""

	def __str__(self):
		return ")"

## Helper functions to return appropriately-typed objects ######################

def do_field_to_value(_s, _l, t):
	"""Constructs a VariableComparison object from a parse action."""

	return VariableComparison(t[0], t[1], t[2])

def do_boolean_operator(_s, _l, t):
	"""Constructs a BooleanOperator object from a parse action."""

	return BooleanOperator(t[0].upper())

def do_boolean_value(s, _l, t):
	"""Constructs a bool object from a parse action."""

	if t[0].lower() == "true":
		return True
	if t[0].lower() == "false":
		return False
	raise Exception("Unknown boolean value: " + s)

def do_integer(_s, _l, t):
	"""Constructs an integer object from a parse action."""

	return int(t[0])

def do_bracket(s, _l, t):
	"""Constructs a StartSubExpression/EndSubExpression object from a parse action."""

	if t[0] == '(':
		return StartSubExpression()
	if t[0] == ')':
		return EndSubExpression()
	raise Exception("Unknown bracketing string: " + s)

################################################################################

class SearchQueryParser:
	"""Parses a search query."""

	tokens = None

	# Pylint seems to think some of the statements below are "pointless"
	# this may be true, but I am not sure how this works... ;)
	# pylint: disable=pointless-statement
	def parse(self, query):
		"""Parses a query string."""

		# Parse instructions
		quoted_string = QuotedString(quoteChar='"', escChar='\\', unquoteResults=True)
		field_name = Word(alphas, alphanums + '_')
		subexpression = Forward()
		boolean_expression = Forward()
		binary_operator = Literal('=') | Literal('<=') | Literal('<') | Literal('>=') | Literal('>')
		boolean_operator = CaselessKeyword('AND') | CaselessKeyword('OR')
		boolean_not = CaselessKeyword('NOT')
		boolean_value = CaselessKeyword("true") ^ CaselessKeyword("false")
		integer = Word(nums)
		rvalue = quoted_string ^ boolean_value ^ integer
		field_to_value = field_name + binary_operator + rvalue
		expression = Optional(boolean_not) + ((subexpression + ZeroOrMore(boolean_expression)) | (field_to_value + ZeroOrMore(boolean_expression)))
		boolean_expression << boolean_operator + expression
		left_bracket = Literal('(')
		right_bracket = Literal(')')
		subexpression << (left_bracket + expression + right_bracket)
		search_query = expression

		# Parse actions for emitting special cases
		field_to_value.setParseAction(do_field_to_value)
		boolean_operator.setParseAction(do_boolean_operator)
		boolean_not.setParseAction(do_boolean_operator)
		boolean_value.setParseAction(do_boolean_value)
		integer.setParseAction(do_integer)
		left_bracket.setParseAction(do_bracket)
		right_bracket.setParseAction(do_bracket)

		self.tokens = search_query.parseString(query)

	def get_tokens(self):
		return self.tokens

	def generate_sql(self, variable_to_column_map):
		sql = ""
		params = []
		for token in self.tokens:
			if isinstance(token, StartSubExpression):
				sql = sql + "("
			elif isinstance(token, EndSubExpression):
				sql = sql + ")"
			elif isinstance(token, VariableComparison):
				if token.left not in variable_to_column_map:
					raise Exception("Unknown variable: " + token.left)

				sql = sql + "`" + variable_to_column_map[token.left] + "` "
				if isinstance(token.right, int):
					sql = sql + token.operator + " %s"
					params.append(token.right)
				elif isinstance(token.right, bool):
					if token.operator == "=":
						sql = sql + "IS "
					elif token.operator == "!=":
						sql = sql + "IS NOT "
					else:
						raise Exception("Operator " + token.operator + " cannot take a boolean")
					if token.right:
						sql = sql + "TRUE"
					else:
						sql = sql + "FALSE"
				else:
					sql = sql + token.operator + " %s"
					params.append(token.right)
			elif isinstance(token, BooleanOperator):
				sql = sql + " " + token.operator + " "
		return (sql, tuple(params))

def get_search_query_sql(query, variable_to_column_map):
	parser = SearchQueryParser()
	parser.parse(query)
	result = parser.generate_sql(variable_to_column_map)
	return result
