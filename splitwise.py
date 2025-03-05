import uuid
from collections import defaultdict
from typing import List, Dict
from abc import ABC
from enum import StrEnum

"""
Core entities:

User --> id,name,balace(user_id:positive or negative amount)
Expense --> id, group_id,splits{user_id:amount_paid},is_settled, payer,metadata ||| 
Group --->id,users,expenses,metadata,balance_sheet ||| add_expense(payer,amount,split_type,metadata),edit_expense(), settle_up()
"""

import uuid
from collections import defaultdict
from typing import List, Dict, Type
from abc import ABC,abstractmethod
from enum import StrEnum

# -------------------- SPLIT STRATEGY --------------------

class SplitType(StrEnum):
    EQUAL = "EQUAL"
    EXACT = "EXACT"
    PERCENTAGE = "PERCENTAGE"
    
class SettlementAlgo(StrEnum):
    HEAP_BASED = "heap_based"
    BRUTE_FORCE = "brute_force"    

class SplitStrategy(ABC):
    _registry: Dict[str, Type["SplitStrategy"]] = {}

    @classmethod
    def register_strategy(cls, split_type: SplitType, strategy_cls: Type["SplitStrategy"]):
        cls._registry[split_type] = strategy_cls

    @classmethod
    def get_strategy(cls, split_type: str) -> Type["SplitStrategy"]:
        if split_type not in cls._registry:
            raise ValueError(f"Invalid split type: {split_type}")
        return cls._registry[split_type]
    @abstractmethod
    def split(self, payer, amount, users, custom_splits=None):
        raise NotImplementedError

class EqualSplit(SplitStrategy):
    def split(self, payer, amount, users, custom_splits=None):
        per_head = amount / len(users)
        return {user: per_head for user in users}

SplitStrategy.register_strategy(SplitType.EQUAL, EqualSplit)

class ExactSplit(SplitStrategy):
    def split(self, payer, amount, users, custom_splits=None):
        if not custom_splits:
            raise ValueError("Custom splits required for ExactSplit")
        if sum(custom_splits.values()) != amount:
            raise ValueError("Custom split amounts do not sum to total amount")
        return custom_splits

SplitStrategy.register_strategy(SplitType.EXACT, ExactSplit)

class PercentageSplit(SplitStrategy):
    def split(self, payer, amount, users, custom_splits=None):
        if not custom_splits:
            raise ValueError("Custom splits required for PercentageSplit")
        if sum(custom_splits.values()) != 100:
            raise ValueError("Percentage splits must sum to 100%")
        return {user: (percent / 100) * amount for user, percent in custom_splits.items()}

SplitStrategy.register_strategy(SplitType.PERCENTAGE, PercentageSplit)

# -------------------- USER CLASS --------------------

class User:
    def __init__(self, name: str):
        self.id = name+" "+str(uuid.uuid4())
        self.name = name
        self.balance = defaultdict(float)  # {user_id: amount}

    def get_balance(self):
        return sum(self.balance.values())

    def __repr__(self):
        return f"User({self.name}, id={self.id})"

class SettlementStrategy(ABC):

    _registry:dict[SettlementAlgo,Type["SettlementStrategy"]] = {}

    @abstractmethod
    def settle( payer: User, payee: User, amount: float, balance_sheet: dict):
        raise NotImplementedError
    
    @classmethod
    def register(cls,settlement_algo:SettlementAlgo,settlement_strategy:Type["SettlementStrategy"]):
        cls._registry[settlement_algo] = settlement_strategy

    @classmethod
    def get_settlement_algo(cls,settlement_algo:SettlementAlgo)->Type["SettlementStrategy"]:
        if settlement_algo in cls._registry:
            return cls._registry[settlement_algo]
        raise ValueError(f"settlement algo doesn't exists {settlement_algo}")


class HeapSettlement(SettlementStrategy):

    def settle( payer: User, payee: User, amount: float,balance_sheet:dict):
        pass 

SettlementStrategy.register(SettlementAlgo.HEAP_BASED,HeapSettlement)

class BruteForceSettlement(SettlementStrategy):

    def settle(self,payer:User, payee:User, amount:float,balance_sheet):
        if payer.id in balance_sheet and payee.id in balance_sheet[payer.id]:
            if balance_sheet[payer.id][payee.id] >= amount:
                balance_sheet[payer.id][payee.id] -= amount
                payee.balance[payer.id] -= amount
                payer.balance[payee.id] -= amount
            else:
                raise ValueError("Settlement amount exceeds the outstanding balance.")
        else:
            raise ValueError("No outstanding balance between these users.")
        
SettlementStrategy.register(SettlementAlgo.BRUTE_FORCE,BruteForceSettlement)

# -------------------- EXPENSE CLASS --------------------

class Expense:
    def __init__(self, payer: User, amount: float, users: List[User], split_strategy: SplitStrategy, custom_splits=None, description: str = ""):
        self.id = str(uuid.uuid4())
        self.payer = payer
        self.amount = amount
        self.splits = split_strategy.split(payer, amount, users, custom_splits)
        self.description = description

    def apply_split(self):
        for user, share in self.splits.items():
            if user == self.payer:
                continue
            user.balance[self.payer.id] -= share
            self.payer.balance[user.id] += share

# -------------------- USER GROUP CLASS --------------------

class UserGroup:
    def __init__(self, name: str, users: List[User],settlement_algo:SettlementAlgo):
        """
        Initialize a new Splitwise instance.

        Args:
            name (str): The name of the Splitwise group.
            users (List[User]): A list of User objects representing the members of the group.
            settlement_algo (SettlementAlgo): The algorithm used to settle balances among users.

        Attributes:
            id (str): A unique identifier for the Splitwise instance.
            name (str): The name of the Splitwise group.
            users (List[User]): A list of User objects representing the members of the group.
            expenses (List): A list to store expenses.
            settlement_algo (SettlementAlgo): The algorithm used to settle balances among users.
            balance_sheet (defaultdict): A nested dictionary to keep track of balances between users.
                The outer dictionary keys are user IDs, and the inner dictionary keys are the IDs of users
                they owe money to, with the values being the amount owed.
        """
        self.id = str(uuid.uuid4())
        self.name = name
        self.users = users
        self.expenses = []
        self.settlement_algo = settlement_algo
        self.balance_sheet = defaultdict(lambda: defaultdict(float))

    def add_expense(self, payer: User, amount: float, split_type: str, custom_splits=None, description: str = ""):
        strategy_class = SplitStrategy.get_strategy(split_type)
        split_strategy = strategy_class()  # Instantiate strategy
        expense = Expense(payer, amount, self.users, split_strategy, custom_splits, description)
        expense.apply_split()
        self.expenses.append(expense)
        for user, share in expense.splits.items():
            if user != payer:
                self.balance_sheet[user.id][payer.id] += share

    def settle_expense(self, payer: User, payee: User, amount: float):
        settlement_strategy = SettlementStrategy.get_settlement_algo(self.settlement_algo)
        settlement_strategy().settle(payer=payer,payee=payee,amount=amount,balance_sheet = self.balance_sheet)

    def get_passbook(self):
        return dict(self.balance_sheet)

    def __repr__(self):
        return f"UserGroup({self.name}, id={self.id})"

# -------------------------- Example Usage --------------------------

# Create Users
alice = User("Alice")
bob = User("Bob")
charlie = User("Charlie")

# Create a Group
trip_group = UserGroup("Goa Trip", [alice, bob, charlie],settlement_algo=SettlementAlgo.BRUTE_FORCE)

# Add Equal Expense
trip_group.add_expense(payer=alice, amount=300, split_type=SplitType.EQUAL)

# Add Exact Split Expense
trip_group.add_expense(
    payer=bob,
    amount=400,
    split_type=SplitType.EXACT,
    custom_splits={alice: 100, bob: 200, charlie: 100},
)

# Add Percentage Split Expense
trip_group.add_expense(
    payer=charlie,
    amount=500,
    split_type=SplitType.PERCENTAGE,
    custom_splits={alice: 40, bob: 40, charlie: 20},
)

# View Balances
print("Passbook:", trip_group.get_passbook())

# Settlement
trip_group.settle_expense(payer=bob, payee=alice, amount=100)

# View Updated Passbook
print("Updated Passbook:", trip_group.get_passbook())
